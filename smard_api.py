from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

APP_TZ = "Europe/Berlin"
HOURS = np.arange(24)
SMARD_BASE_URL = "https://www.smard.de/app/chart_data"
SMARD_REGION = "DE"
SMARD_RESOLUTION = "hour"

# SMARD dient hier nur als Orientierungsquelle für Last, Wind und PV.
# Importe/Exporte und Restkategorien werden absichtlich nicht geladen.
SMARD_FILTERS = {
    "wind_offshore": 1225,
    "wind_onshore": 4067,
    "pv": 4068,
    "load": 410,
}

FILTER_LABELS = {
    "wind_offshore": "Wind Offshore",
    "wind_onshore": "Wind Onshore",
    "pv": "Photovoltaik",
    "load": "Netzlast",
}


@dataclass(frozen=True)
class SmardSeriesResult:
    key: str
    filter_id: int
    values: pd.Series
    used_index_timestamp: int
    url: str


def _require_requests() -> None:
    if requests is None:
        raise RuntimeError("Das Paket 'requests' fehlt. Ergänze es in requirements.txt.")


def _http_get_json(url: str, timeout_s: int = 20) -> dict[str, Any] | list[Any]:
    _require_requests()
    headers = {"User-Agent": "TH-Bingen-REi-Streamlit/1.0"}
    response = requests.get(url, timeout=timeout_s, headers=headers)
    response.raise_for_status()
    return response.json()


def _extract_timestamps(payload: dict[str, Any] | list[Any]) -> list[int]:
    if isinstance(payload, list):
        data = payload
    elif isinstance(payload, dict):
        data = []
        for key in ("timestamps", "timestamp", "indices", "index", "data"):
            if key in payload:
                data = payload[key]
                break
    else:
        data = []

    out: list[int] = []
    for item in data:
        if isinstance(item, dict):
            val = item.get("timestamp", item.get("date", item.get("ts")))
        else:
            val = item
        try:
            out.append(int(val))
        except (TypeError, ValueError):
            continue
    return sorted(set(out))


def _extract_time_series(payload: dict[str, Any] | list[Any]) -> list[tuple[int, float]]:
    if isinstance(payload, dict):
        raw = []
        for key in ("series", "values", "data"):
            if key in payload:
                raw = payload[key]
                break
    else:
        raw = payload

    pairs: list[tuple[int, float]] = []
    for item in raw:
        if isinstance(item, dict):
            ts = item.get("timestamp", item.get("date", item.get("x")))
            value = item.get("value", item.get("y"))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            ts, value = item[0], item[1]
        else:
            continue

        if value is None:
            continue
        try:
            pairs.append((int(ts), float(value)))
        except (TypeError, ValueError):
            continue
    return pairs


def _target_timestamp_ms(day: date) -> int:
    return int(pd.Timestamp(day, tz=APP_TZ).timestamp() * 1000)


def smard_index(filter_id: int, region: str = SMARD_REGION, resolution: str = SMARD_RESOLUTION) -> list[int]:
    url = f"{SMARD_BASE_URL}/{filter_id}/{region}/index_{resolution}.json"
    payload = _http_get_json(url)
    timestamps = _extract_timestamps(payload)
    if not timestamps:
        raise RuntimeError(f"SMARD-Index leer für Filter {filter_id}.")
    return timestamps


def _choose_index_timestamp(index_values: list[int], target_ms: int) -> int:
    earlier = [ts for ts in index_values if ts <= target_ms]
    if earlier:
        return max(earlier)
    return min(index_values)


def smard_load_series(
    key: str,
    filter_id: int,
    day_iso: str,
    region: str = SMARD_REGION,
    resolution: str = SMARD_RESOLUTION,
) -> SmardSeriesResult:
    day = date.fromisoformat(day_iso)
    target_ms = _target_timestamp_ms(day)
    idx = smard_index(filter_id, region=region, resolution=resolution)
    used_ts = _choose_index_timestamp(idx, target_ms)

    url = f"{SMARD_BASE_URL}/{filter_id}/{region}/{filter_id}_{region}_{resolution}_{used_ts}.json"
    payload = _http_get_json(url)
    pairs = _extract_time_series(payload)
    if not pairs:
        raise RuntimeError(f"Keine SMARD-Zeitreihe für {FILTER_LABELS.get(key, key)} ({filter_id}).")

    ts = pd.to_datetime([p[0] for p in pairs], unit="ms", utc=True).tz_convert(APP_TZ)
    vals = pd.to_numeric(pd.Series([p[1] for p in pairs], index=ts), errors="coerce").fillna(0.0)
    vals = vals[vals.index.date == day]

    if vals.empty:
        raw = pd.Series([p[1] for p in pairs], index=pd.to_datetime([p[0] for p in pairs], unit="ms", utc=True))
        vals = pd.to_numeric(raw, errors="coerce").fillna(0.0)
        vals = vals[vals.index.date == day]

    return SmardSeriesResult(key=key, filter_id=filter_id, values=vals, used_index_timestamp=used_ts, url=url)


def _series_to_24h_gw(values: pd.Series) -> pd.Series:
    if values.empty:
        return pd.Series(0.0, index=HOURS, dtype=float)
    if not isinstance(values.index, pd.DatetimeIndex):
        raise TypeError("SMARD-Zeitreihe braucht DatetimeIndex.")

    # Bei stündlicher SMARD-Auflösung sind die Werte MWh je Stunde; numerisch entspricht das MW.
    by_hour = values.groupby(values.index.hour).mean() / 1000.0
    by_hour = by_hour.reindex(HOURS)
    if by_hour.isna().any():
        by_hour = by_hour.interpolate(limit_direction="both").fillna(0.0)
    return by_hour.astype(float)


def load_smard_api_profile(day_iso: str, region: str = SMARD_REGION) -> tuple[pd.DataFrame, pd.DataFrame]:
    results: dict[str, SmardSeriesResult] = {}
    meta_rows: list[dict[str, Any]] = []

    for key, filter_id in SMARD_FILTERS.items():
        result = smard_load_series(key=key, filter_id=filter_id, day_iso=day_iso, region=region)
        results[key] = result
        meta_rows.append({
            "Kategorie": FILTER_LABELS.get(key, key),
            "Filter": filter_id,
            "Werte": int(len(result.values)),
            "IndexTimestamp": result.used_index_timestamp,
            "URL": result.url,
        })

    wind = _series_to_24h_gw(results["wind_offshore"].values) + _series_to_24h_gw(results["wind_onshore"].values)
    pv = _series_to_24h_gw(results["pv"].values)
    load = _series_to_24h_gw(results["load"].values)

    profile = pd.DataFrame({
        "Stunde": HOURS.astype(int),
        "Last_GW": load.to_numpy(dtype=float),
        "Wind_GW": wind.to_numpy(dtype=float),
        "PV_GW": pv.to_numpy(dtype=float),
        "Konv_GW": np.zeros(24, dtype=float),
        "BESS_GW": np.zeros(24, dtype=float),
    })
    profile["SMARD_EE_Orientierung_GW"] = profile["Wind_GW"] + profile["PV_GW"]
    profile["SMARD_Zielluecke_GW"] = profile["Last_GW"] - profile["SMARD_EE_Orientierung_GW"]
    profile["timestamp"] = pd.to_datetime(day_iso) + pd.to_timedelta(profile["Stunde"], unit="h")

    return profile, pd.DataFrame(meta_rows)
