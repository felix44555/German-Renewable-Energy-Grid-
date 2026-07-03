from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import pypsa
except ImportError:  # pragma: no cover
    pypsa = None


FALLBACK_REFS = {
    "wind_gw": 70.0,
    "pv_gw": 90.0,
    "konv_gw": 80.0,
    "bess_gw": 12.0,
    "bess_gwh": 24.0,
    "load_mean_gw": 60.0,
}


def load_pypsa_network(path: str | Path):
    if pypsa is None:
        raise RuntimeError("PyPSA ist nicht installiert. Ergänze 'pypsa' in requirements.txt.")
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Netzdatei nicht gefunden: {path.name}. Lege {path.name} in denselben Ordner wie app.py.")
    return pypsa.Network(path)


def carrier_to_typ(carrier: object) -> str:
    c = str(carrier).lower()
    if "wind" in c or "offshore" in c or "onshore" in c:
        return "Wind"
    if "solar" in c or "pv" in c or "photovoltaic" in c:
        return "PV"
    if "battery" in c or "bess" in c or "storage" in c:
        return "BESS"
    if "load_shedding" in c or "load shedding" in c:
        return "Lastabwurf"
    if "import" in c or "export" in c:
        return "Import/Export"
    return "Konventionell"


def _component_capacity_mw(row: pd.Series, candidates: tuple[str, ...]) -> float:
    for col in candidates:
        if col in row.index and pd.notna(row[col]):
            try:
                val = float(row[col])
            except (TypeError, ValueError):
                continue
            if val > 0:
                return val
    return 0.0


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(out):
        return default
    return out


def _require_bus_coordinates(n: Any) -> None:
    if "x" not in n.buses.columns or "y" not in n.buses.columns:
        raise ValueError("Die PyPSA-Busse brauchen Koordinaten: n.buses.x und n.buses.y.")
    missing = n.buses[["x", "y"]].isna().any(axis=1)
    if bool(missing.any()):
        bad = ", ".join(map(str, n.buses.index[missing].tolist()))
        raise ValueError(f"Folgende Busse haben fehlende Koordinaten: {bad}")


def _load_by_bus_mw(n: Any) -> pd.Series:
    buses = n.buses.index.astype(str)
    result = pd.Series(0.0, index=buses, dtype=float)
    if n.loads.empty:
        return result

    if "p_set" in n.loads.columns:
        static = pd.to_numeric(n.loads["p_set"], errors="coerce").fillna(0.0)
    else:
        static = pd.Series(0.0, index=n.loads.index, dtype=float)

    try:
        ts = n.loads_t.p_set
        if isinstance(ts, pd.DataFrame) and not ts.empty:
            ts_mean = ts.mean(axis=0).reindex(n.loads.index).fillna(0.0)
            if float(ts_mean.sum()) > 0:
                static = ts_mean
    except Exception:
        pass

    tmp = pd.DataFrame({"bus": n.loads["bus"].astype(str), "p_mw": static.astype(float)})
    grouped = tmp.groupby("bus")["p_mw"].sum()
    return grouped.reindex(result.index).fillna(0.0)


def pypsa_to_consumers(n: Any) -> pd.DataFrame:
    _require_bus_coordinates(n)
    buses = n.buses.copy()
    load_by_bus = _load_by_bus_mw(n)
    df = pd.DataFrame({
        "Bus": buses.index.astype(str),
        "Cluster": buses.index.astype(str),
        "lat": pd.to_numeric(buses["y"], errors="coerce").astype(float),
        "lon": pd.to_numeric(buses["x"], errors="coerce").astype(float),
        "Last_MW": load_by_bus.reindex(buses.index.astype(str)).fillna(0.0).to_numpy(),
    })
    total = float(df["Last_MW"].sum())
    df["Anteil"] = df["Last_MW"] / total if total > 0 else 1.0 / max(len(df), 1)
    return df[["Bus", "Cluster", "lat", "lon", "Anteil"]]


def pypsa_to_lines(n: Any) -> pd.DataFrame:
    _require_bus_coordinates(n)
    buses = n.buses.copy()
    bus_index = set(buses.index.astype(str))
    rows: list[dict[str, object]] = []

    if hasattr(n, "lines") and not n.lines.empty:
        for name, ln in n.lines.iterrows():
            bus0 = str(ln["bus0"])
            bus1 = str(ln["bus1"])
            if bus0 not in bus_index or bus1 not in bus_index:
                continue
            b0 = buses.loc[bus0]
            b1 = buses.loc[bus1]
            #hier nur halbe Kapazität importiert
            cap_mw = 0.5 * _component_capacity_mw(ln, ("s_nom", "s_nom_opt", "p_nom", "p_nom_opt"))
            rows.append({
                "Name": str(name),
                "Typ": "Line",
                "von": bus0,
                "nach": bus1,
                "lat0": float(b0["y"]),
                "lon0": float(b0["x"]),
                "lat1": float(b1["y"]),
                "lon1": float(b1["x"]),
                "Kapazitaet_GW": cap_mw / 1000.0,
                "X_Ohm": _as_float(ln.get("x", np.nan), np.nan),
                "R_Ohm": _as_float(ln.get("r", np.nan), np.nan),
                "B_Siemens": _as_float(ln.get("b", np.nan), np.nan),
                "V_nom_kV": _as_float(ln.get("v_nom", 380.0), 380.0),
                "Laenge_km": _as_float(ln.get("length", np.nan), np.nan),
                "Num_parallel": _as_float(ln.get("num_parallel", 1.0), 1.0),
            })

    if hasattr(n, "links") and not n.links.empty:
        for name, lk in n.links.iterrows():
            bus0 = str(lk["bus0"])
            bus1 = str(lk["bus1"])
            if bus0 not in bus_index or bus1 not in bus_index:
                continue
            b0 = buses.loc[bus0]
            b1 = buses.loc[bus1]
            cap_mw = _component_capacity_mw(lk, ("p_nom", "p_nom_opt", "s_nom", "s_nom_opt"))
            rows.append({
                "Name": f"Link {name}",
                "Typ": "Link",
                "von": bus0,
                "nach": bus1,
                "lat0": float(b0["y"]),
                "lon0": float(b0["x"]),
                "lat1": float(b1["y"]),
                "lon1": float(b1["x"]),
                "Kapazitaet_GW": cap_mw / 1000.0,
                "X_Ohm": np.nan,
                "R_Ohm": np.nan,
                "B_Siemens": np.nan,
                "V_nom_kV": 380.0,
                "Laenge_km": np.nan,
                "Num_parallel": 1.0,
            })

    # 1. Tabelle erstellen und in einer Variable (df) zwischenspeichern
    df = pd.DataFrame(rows, columns=[
        "Name", "Typ", "von", "nach", "lat0", "lon0", "lat1", "lon1",
        "Kapazitaet_GW", "X_Ohm", "R_Ohm", "B_Siemens", "V_nom_kV", "Laenge_km", "Num_parallel",
    ])

    # 2. Den Wert manuell überschreiben (z.B. Kapazität auf 5.0 GW setzen)
    # Syntax-Logik: df.loc[ZEILEN_BEDINGUNG, SPALTEN_NAME] = NEUER_WERT
    df.loc[df["Name"] == "merged_line_0", "Kapazitaet_GW"] *= 0.5

    # 3. Das manipulierte Objekt zurückgeben
    return df
   # return pd.DataFrame(rows, columns=[
    #    "Name", "Typ", "von", "nach", "lat0", "lon0", "lat1", "lon1",
     #   "Kapazitaet_GW", "X_Ohm", "R_Ohm", "B_Siemens", "V_nom_kV", "Laenge_km", "Num_parallel",
    #])


def pypsa_to_generators(n: Any) -> pd.DataFrame:
    _require_bus_coordinates(n)
    buses = n.buses.copy()
    bus_index = set(buses.index.astype(str))
    rows: list[dict[str, object]] = []

    if hasattr(n, "generators") and not n.generators.empty:
        for name, gen in n.generators.iterrows():
            bus = str(gen["bus"])
            if bus not in bus_index:
                continue
            typ = carrier_to_typ(gen.get("carrier", ""))
            b = buses.loc[bus]
            p_nom_mw = _component_capacity_mw(gen, ("p_nom", "p_nom_opt"))
            rows.append({
                "Name": str(name),
                "Bus": bus,
                "Typ": typ,
                "lat": float(b["y"]),
                "lon": float(b["x"]),
                "p_nom_MW": p_nom_mw,
            })

    if hasattr(n, "storage_units") and not n.storage_units.empty:
        for name, su in n.storage_units.iterrows():
            bus = str(su["bus"])
            if bus not in bus_index:
                continue
            b = buses.loc[bus]
            p_nom_mw = _component_capacity_mw(su, ("p_nom", "p_nom_opt"))
            rows.append({
                "Name": str(name),
                "Bus": bus,
                "Typ": "BESS",
                "lat": float(b["y"]),
                "lon": float(b["x"]),
                "p_nom_MW": p_nom_mw,
            })

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["Name", "Bus", "Typ", "lat", "lon", "Anteil", "p_nom_MW"])

    df["Anteil"] = 0.0
    for typ in df["Typ"].unique():
        mask = df["Typ"] == typ
        total = float(df.loc[mask, "p_nom_MW"].sum())
        df.loc[mask, "Anteil"] = df.loc[mask, "p_nom_MW"] / total if total > 0 else 1.0 / int(mask.sum())

    return df[["Name", "Bus", "Typ", "lat", "lon", "Anteil", "p_nom_MW"]]


def ensure_bess_visible(generators: pd.DataFrame, consumers: pd.DataFrame) -> pd.DataFrame:
    if not generators.empty and bool((generators["Typ"] == "BESS").any()):
        return generators
    if consumers.empty:
        return generators

    top = consumers.sort_values("Anteil", ascending=False).head(min(4, len(consumers))).copy()
    total = float(top["Anteil"].sum())
    rows = []
    for _, row in top.iterrows():
        rows.append({
            "Name": f"BESS Stellgröße {row['Bus']}",
            "Bus": row["Bus"],
            "Typ": "BESS",
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "Anteil": float(row["Anteil"]) / total if total > 0 else 1.0 / len(top),
            "p_nom_MW": np.nan,
        })
    return pd.concat([generators, pd.DataFrame(rows)], ignore_index=True)


def get_reference_values(n: Any) -> dict[str, float]:
    refs = dict(FALLBACK_REFS)

    if hasattr(n, "generators") and not n.generators.empty:
        gens = n.generators.copy()
        gens["Typ"] = gens["carrier"].apply(carrier_to_typ) if "carrier" in gens.columns else "Konventionell"
        gens["cap_mw"] = gens.apply(lambda r: _component_capacity_mw(r, ("p_nom", "p_nom_opt")), axis=1)
        for typ, key in (("Wind", "wind_gw"), ("PV", "pv_gw"), ("Konventionell", "konv_gw"), ("BESS", "bess_gw")):
            val = float(gens.loc[gens["Typ"] == typ, "cap_mw"].sum()) / 1000.0
            if val > 0:
                refs[key] = val

    if hasattr(n, "storage_units") and not n.storage_units.empty:
        su = n.storage_units.copy()
        p_nom_mw = su.apply(lambda r: _component_capacity_mw(r, ("p_nom", "p_nom_opt")), axis=1)
        bess_gw = float(p_nom_mw.sum()) / 1000.0
        if bess_gw > 0:
            refs["bess_gw"] = bess_gw
        if "max_hours" in su.columns:
            max_hours = pd.to_numeric(su["max_hours"], errors="coerce").fillna(0.0)
            bess_gwh = float((p_nom_mw * max_hours).sum()) / 1000.0
            if bess_gwh > 0:
                refs["bess_gwh"] = bess_gwh

    load_total_gw = float(_load_by_bus_mw(n).sum()) / 1000.0
    if load_total_gw > 0:
        refs["load_mean_gw"] = load_total_gw

    for key, fallback in FALLBACK_REFS.items():
        if refs.get(key, 0.0) <= 0:
            refs[key] = fallback
    return refs
