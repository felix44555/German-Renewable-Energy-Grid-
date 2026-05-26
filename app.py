from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    import pypsa
except ImportError:
    pypsa = None

from scenario_tools import (
    SCENARIOS,
    apply_scenario_to_profiles,
    compute_line_status_proxy,
    evaluate_scenario,
)


# =============================================================================
# Konfiguration
# =============================================================================
BASE_DIR = Path(__file__).resolve().parent
NETWORK_FILE = BASE_DIR / "real_germany_8n_configured.nc"

HOURS = np.arange(24)

# Fallback-Werte, falls die .nc-Datei keine brauchbaren Kapazitäten enthält.
FALLBACK_REFS = {
    "wind_gw": 70.0,
    "pv_gw": 90.0,
    "konv_gw": 80.0,
    "bess_gw": 12.0,
    "bess_gwh": 17.0,
    "load_mean_gw": 60.0,
}


# =============================================================================
# Laden des PyPSA-Netzes
# =============================================================================
@st.cache_resource(show_spinner=False)
def load_pypsa_network(path: str | Path):
    """Lädt ein PyPSA-Netz aus einer NetCDF-Datei."""
    if pypsa is None:
        raise RuntimeError(
            "PyPSA ist nicht installiert. Ergänze 'pypsa' in requirements.txt."
        )

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Netzdatei nicht gefunden: {path.name}. "
            "Lege simplified_germany_8node.nc in denselben Ordner wie diese Python-Datei."
        )

    return pypsa.Network(path)


# =============================================================================
# PyPSA -> App-Datenmodell
# =============================================================================
def carrier_to_typ(carrier: object) -> str:
    """Ordnet PyPSA-carrier auf die vier App-Typen zu."""
    c = str(carrier).lower()

    if "wind" in c or "offshore" in c or "onshore" in c:
        return "Wind"
    if "solar" in c or "pv" in c or "photovoltaic" in c:
        return "PV"
    if "battery" in c or "bess" in c or "storage" in c:
        return "BESS"

    return "Konventionell"


def _component_capacity_mw(row: pd.Series, candidates: tuple[str, ...]) -> float:
    """Robustes Auslesen einer Leistungs-/Energienennwert-Spalte."""
    for col in candidates:
        if col in row.index and pd.notna(row[col]):
            try:
                val = float(row[col])
            except (TypeError, ValueError):
                continue
            if val > 0:
                return val
    return 0.0


def _require_bus_coordinates(n) -> None:
    if "x" not in n.buses.columns or "y" not in n.buses.columns:
        raise ValueError("Die PyPSA-Busse brauchen Koordinaten: n.buses.x und n.buses.y.")

    missing = n.buses[["x", "y"]].isna().any(axis=1)
    if bool(missing.any()):
        bad = ", ".join(map(str, n.buses.index[missing].tolist()))
        raise ValueError(f"Folgende Busse haben fehlende Koordinaten: {bad}")


def _load_by_bus_mw(n) -> pd.Series:
    """Bestimmt eine repräsentative Last je Bus in MW."""
    buses = n.buses.index.astype(str)
    result = pd.Series(0.0, index=buses, dtype=float)

    if n.loads.empty:
        return result

    # 1) statischer Wert n.loads.p_set
    if "p_set" in n.loads.columns:
        static = pd.to_numeric(n.loads["p_set"], errors="coerce").fillna(0.0)
    else:
        static = pd.Series(0.0, index=n.loads.index, dtype=float)

    # 2) falls vorhanden: Mittelwert der Zeitreihe n.loads_t.p_set
    try:
        ts = n.loads_t.p_set
        if isinstance(ts, pd.DataFrame) and not ts.empty:
            ts_mean = ts.mean(axis=0).reindex(n.loads.index).fillna(0.0)
            if float(ts_mean.sum()) > 0:
                static = ts_mean
    except Exception:
        pass

    tmp = pd.DataFrame({
        "bus": n.loads["bus"].astype(str),
        "p_mw": static.astype(float),
    })

    grouped = tmp.groupby("bus")["p_mw"].sum()
    return grouped.reindex(result.index).fillna(0.0)


def pypsa_to_consumers(n) -> pd.DataFrame:
    """
    Erzeugt Verbraucher-Cluster aus PyPSA-Bussen.
    PyPSA-Konvention: bus.x = Longitude, bus.y = Latitude.
    """
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
    if total > 0:
        df["Anteil"] = df["Last_MW"] / total
    else:
        df["Anteil"] = 1.0 / max(len(df), 1)

    return df[["Bus", "Cluster", "lat", "lon", "Anteil"]]


def pypsa_to_lines(n) -> pd.DataFrame:
    """Konvertiert PyPSA-Lines und Links zu Kartenleitungen."""
    _require_bus_coordinates(n)

    buses = n.buses.copy()
    bus_index = buses.index.astype(str)
    rows: list[dict[str, object]] = []

    if hasattr(n, "lines") and not n.lines.empty:
        for name, ln in n.lines.iterrows():
            bus0 = str(ln["bus0"])
            bus1 = str(ln["bus1"])
            if bus0 not in bus_index or bus1 not in bus_index:
                continue

            b0 = buses.loc[bus0]
            b1 = buses.loc[bus1]
            cap_mw = _component_capacity_mw(ln, ("s_nom", "s_nom_opt", "p_nom", "p_nom_opt"))

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
            })

    # Links werden in PyPSA oft für HGÜ/Konverter verwendet.
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
            })

    return pd.DataFrame(rows, columns=[
        "Name", "Typ", "von", "nach", "lat0", "lon0", "lat1", "lon1", "Kapazitaet_GW"
    ])


def pypsa_to_generators(n) -> pd.DataFrame:
    """Konvertiert PyPSA-Generatoren und StorageUnits zu App-Erzeugern."""
    _require_bus_coordinates(n)

    buses = n.buses.copy()
    bus_index = buses.index.astype(str)
    rows: list[dict[str, object]] = []

    if hasattr(n, "generators") and not n.generators.empty:
        for name, gen in n.generators.iterrows():
            bus = str(gen["bus"])
            if bus not in bus_index:
                continue

            b = buses.loc[bus]
            typ = carrier_to_typ(gen.get("carrier", ""))
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
        return pd.DataFrame(columns=["Name", "Bus", "Typ", "lat", "lon", "Anteil"])

    df["Anteil"] = 0.0
    for typ in df["Typ"].unique():
        mask = df["Typ"] == typ
        total = float(df.loc[mask, "p_nom_MW"].sum())
        if total > 0:
            df.loc[mask, "Anteil"] = df.loc[mask, "p_nom_MW"] / total
        else:
            df.loc[mask, "Anteil"] = 1.0 / int(mask.sum())

    return df[["Name", "Bus", "Typ", "lat", "lon", "Anteil"]]


def get_reference_values(n) -> dict[str, float]:
    """Ermittelt Referenzwerte aus dem PyPSA-Netz; nutzt Fallbacks bei fehlenden Daten."""
    refs = dict(FALLBACK_REFS)

    if hasattr(n, "generators") and not n.generators.empty:
        gens = n.generators.copy()
        if "carrier" in gens.columns:
            gens["Typ"] = gens["carrier"].apply(carrier_to_typ)
        else:
            gens["Typ"] = "Konventionell"

        gens["cap_mw"] = gens.apply(
            lambda r: _component_capacity_mw(r, ("p_nom", "p_nom_opt")), axis=1
        )

        wind = float(gens.loc[gens["Typ"] == "Wind", "cap_mw"].sum()) / 1000.0
        pv = float(gens.loc[gens["Typ"] == "PV", "cap_mw"].sum()) / 1000.0
        konv = float(gens.loc[gens["Typ"] == "Konventionell", "cap_mw"].sum()) / 1000.0
        bess_from_gen = float(gens.loc[gens["Typ"] == "BESS", "cap_mw"].sum()) / 1000.0

        if wind > 0:
            refs["wind_gw"] = wind
        if pv > 0:
            refs["pv_gw"] = pv
        if konv > 0:
            refs["konv_gw"] = konv
        if bess_from_gen > 0:
            refs["bess_gw"] = bess_from_gen

    if hasattr(n, "storage_units") and not n.storage_units.empty:
        su = n.storage_units.copy()
        p_nom_mw = su.apply(lambda r: _component_capacity_mw(r, ("p_nom", "p_nom_opt")), axis=1)
        bess_gw = float(p_nom_mw.sum()) / 1000.0
        if bess_gw > 0:
            refs["bess_gw"] = bess_gw

        # PyPSA StorageUnit: max_hours * p_nom ergibt grob Energieinhalt.
        if "max_hours" in su.columns:
            max_hours = pd.to_numeric(su["max_hours"], errors="coerce").fillna(0.0)
            bess_gwh = float((p_nom_mw * max_hours).sum()) / 1000.0
            if bess_gwh > 0:
                refs["bess_gwh"] = bess_gwh

    load_by_bus = _load_by_bus_mw(n)
    load_total_gw = float(load_by_bus.sum()) / 1000.0
    if load_total_gw > 0:
        refs["load_mean_gw"] = load_total_gw

    for key, fallback in FALLBACK_REFS.items():
        if refs.get(key, 0.0) <= 0:
            refs[key] = fallback

    return refs


# =============================================================================
# Profile und Dispatch
# =============================================================================
def generate_profiles(
    wind_scale: float,
    pv_scale: float,
    load_scale: float,
    refs: dict[str, float],
    seed: int = 7,
) -> pd.DataFrame:
    """Erzeugt synthetische 24-h-Profile auf Basis der Netz-Referenzwerte."""
    rng = np.random.default_rng(seed)
    h = HOURS

    # Basisform ähnlich dem ursprünglichen Skript, aber auf Netz-Last normiert.
    raw_load_shape = (
        55.0
        + 12.0 * np.exp(-((h - 8) ** 2) / 6.0)
        + 8.0 * np.exp(-((h - 13) ** 2) / 10.0)
        + 18.0 * np.exp(-((h - 19) ** 2) / 5.0)
    )
    raw_load_shape = raw_load_shape / float(np.mean(raw_load_shape))
    load = refs["load_mean_gw"] * load_scale * raw_load_shape

    pv_shape = np.where((h >= 6) & (h <= 20), np.exp(-((h - 13) ** 2) / 9.0), 0.0)
    pv_peak_factor = 0.55
    pv_total = refs["pv_gw"] * pv_scale * pv_peak_factor * pv_shape

    raw_wind = rng.normal(loc=0.45, scale=0.18, size=24)
    wind_factor = np.convolve(raw_wind, np.ones(5) / 5.0, mode="same")
    wind_factor = np.clip(wind_factor, 0.08, 0.85)
    wind_total = refs["wind_gw"] * wind_scale * wind_factor

    return pd.DataFrame({
        "Stunde": h,
        "Last_GW": load,
        "PV_GW": pv_total,
        "Wind_GW": wind_total,
    })


def compute_konv_grundlast(
    load: np.ndarray,
    konv_max_gw: float,
    grundlast_anteil: float = 0.55,
    grundlast_min_anteil: float = 0.30,
    traegheit: float = 0.25,
) -> np.ndarray:
    """Modelliert konventionelle Erzeugung als träge Grundlast."""
    target = grundlast_anteil * load
    min_level = grundlast_min_anteil * float(np.mean(load))
    target = np.maximum(target, min_level)

    konv = np.zeros_like(target, dtype=float)
    konv[0] = target[0]
    alpha = float(np.clip(traegheit, 0.05, 1.0))

    for i in range(1, len(target)):
        konv[i] = konv[i - 1] + alpha * (target[i] - konv[i - 1])

    return np.minimum(konv, konv_max_gw)


def simulate_dispatch(
    df: pd.DataFrame,
    bess_scale: float,
    refs: dict[str, float],
    soc_start_pct: float = 50.0,
    eta: float = 0.9,
    grundlast_anteil: float = 0.55,
    grundlast_min_anteil: float = 0.30,
    traegheit: float = 0.25,
) -> pd.DataFrame:
    """
    Vereinfachter Dispatch:
    Konventionelle Grundlast + Wind/PV + BESS-Ausgleich + konventionelle Spitze.
    Keine echte Lastflussrechnung.
    """
    p_bess_max = refs["bess_gw"] * bess_scale
    cap_bess = refs["bess_gwh"] * bess_scale
    soc = cap_bess * soc_start_pct / 100.0
    soc_min = 0.10 * cap_bess
    soc_max = 0.95 * cap_bess

    konv_base = compute_konv_grundlast(
        df["Last_GW"].to_numpy(),
        konv_max_gw=refs["konv_gw"],
        grundlast_anteil=grundlast_anteil,
        grundlast_min_anteil=grundlast_min_anteil,
        traegheit=traegheit,
    )

    konv_total: list[float] = []
    konv_spitze: list[float] = []
    bess_p: list[float] = []
    curtail: list[float] = []
    soc_track: list[float] = []
    bilanz: list[float] = []
    status: list[str] = []

    for i, row in df.iterrows():
        load = float(row["Last_GW"])
        pv = float(row["PV_GW"])
        wind = float(row["Wind_GW"])
        k_base = float(konv_base[i])

        residual = load - k_base - pv - wind

        if cap_bess <= 0 or p_bess_max <= 0:
            b_power = 0.0
        elif residual < -1e-9:
            charge_power = min(-residual, p_bess_max)
            energy_stored = charge_power * eta
            if soc + energy_stored > soc_max:
                energy_stored = max(soc_max - soc, 0.0)
                charge_power = energy_stored / eta if eta > 0 else 0.0
            soc += energy_stored
            b_power = -charge_power
        elif residual > 1e-9:
            discharge_power = min(residual, p_bess_max)
            energy_taken = discharge_power / eta
            if soc - energy_taken < soc_min:
                energy_taken = max(soc - soc_min, 0.0)
                discharge_power = energy_taken * eta
            soc -= energy_taken
            b_power = discharge_power
        else:
            b_power = 0.0

        residual2 = residual - b_power

        spitze = 0.0
        if residual2 > 1e-9:
            free_konv = max(refs["konv_gw"] - k_base, 0.0)
            spitze = min(residual2, free_konv)

        k_ges = k_base + spitze

        cur = 0.0
        if residual2 < -1e-9 and b_power <= 0.0:
            cur = -residual2

        gen_eff = pv + wind + k_ges + max(b_power, 0.0) - cur
        charging = max(-b_power, 0.0)
        nb = gen_eff - charging - load

        if nb < -1.0:
            stat = "kritisch"
        elif cur > 0.5:
            stat = "Abregelung"
        elif nb > 1.0:
            stat = "Ueberschuss"
        else:
            stat = "stabil"

        konv_total.append(k_ges)
        konv_spitze.append(spitze)
        bess_p.append(b_power)
        curtail.append(cur)
        soc_track.append(soc)
        bilanz.append(nb)
        status.append(stat)

    out = df.copy()
    out["Konv_Grundlast_GW"] = konv_base
    out["Konv_Spitze_GW"] = konv_spitze
    out["Konv_GW"] = konv_total
    out["BESS_GW"] = bess_p
    out["BESS_Laden_GW"] = [max(-x, 0.0) for x in bess_p]
    out["BESS_Entladen_GW"] = [max(x, 0.0) for x in bess_p]
    out["Curtailment_GW"] = curtail
    out["SOC_GWh"] = soc_track
    out["SOC_pct"] = [s / cap_bess * 100.0 if cap_bess > 0 else 0.0 for s in soc_track]
    out["Netzbilanz_GW"] = bilanz
    out["Status"] = status
    return out


# =============================================================================
# Darstellung
# =============================================================================
TYP_COLORS = {
    "Wind": "#1f77b4",
    "PV": "#ff7f0e",
    "BESS": "#2ca02c",
    "Konventionell": "#7f7f7f",
    "Verbraucher": "#d62728",
    "Leitung": "#444444",
}

TYP_SYMBOLS = {
    "Wind": "triangle-up",
    "PV": "square",
    "BESS": "diamond",
    "Konventionell": "circle",
    "Verbraucher": "star",
}


# Visuelle Marker-Versetzung:
# Die PyPSA-Komponenten liegen fachlich weiterhin auf ihrem Bus.
# Nur für die Kartenanzeige werden Wind/PV/BESS/Konventionell leicht um den Bus herum verteilt.
MARKER_OFFSET_DIRECTIONS = {
    "Wind": (-1.0, 1.0),
    "PV": (1.0, 1.0),
    "BESS": (1.0, -1.0),
    "Konventionell": (-1.0, -1.0),
}


def apply_marker_offsets(
    df: pd.DataFrame,
    lon_col: str = "lon",
    lat_col: str = "lat",
    typ_col: str = "Typ",
    bus_col: str = "Bus",
    offset_deg: float = 0.18,
    intra_type_spread_deg: float = 0.035,
) -> pd.DataFrame:
    """
    Versetzt Marker nur für die Visualisierung.

    Grund:
    In aggregierten PyPSA-Netzen hängen Wind, PV, BESS und konventionelle
    Erzeugung oft am selben Bus. Ohne Versatz liegen die Symbole exakt
    übereinander und sind nicht unterscheidbar.

    Die Originalkoordinaten bleiben in lon/lat erhalten.
    Die Anzeige nutzt plot_lon/plot_lat.
    """
    out = df.copy()

    if out.empty:
        out["plot_lon"] = []
        out["plot_lat"] = []
        return out

    out["plot_lon"] = pd.to_numeric(out[lon_col], errors="coerce").astype(float)
    out["plot_lat"] = pd.to_numeric(out[lat_col], errors="coerce").astype(float)

    # Hauptversatz nach Technologie.
    for typ, (dx, dy) in MARKER_OFFSET_DIRECTIONS.items():
        mask = out[typ_col] == typ
        if not bool(mask.any()):
            continue

        lat_rad = np.deg2rad(out.loc[mask, lat_col].astype(float))
        # Längengrade werden in Deutschland nach Norden enger; daher cos(lat)-Korrektur.
        lon_scale = np.maximum(np.cos(lat_rad), 0.35)

        out.loc[mask, "plot_lon"] = (
            out.loc[mask, lon_col].astype(float) + dx * offset_deg / lon_scale
        )
        out.loc[mask, "plot_lat"] = (
            out.loc[mask, lat_col].astype(float) + dy * offset_deg
        )

    # Falls mehrere Marker desselben Typs am selben Bus hängen, leicht zusätzlich auffächern.
    if bus_col in out.columns:
        grouped = out.groupby([bus_col, typ_col], sort=False)
        for _, idx in grouped.groups.items():
            idx = list(idx)
            if len(idx) <= 1:
                continue

            angles = np.linspace(0.0, 2.0 * np.pi, len(idx), endpoint=False)
            lat_rad = np.deg2rad(out.loc[idx, lat_col].astype(float))
            lon_scale = np.maximum(np.cos(lat_rad), 0.35)

            out.loc[idx, "plot_lon"] = (
                out.loc[idx, "plot_lon"].to_numpy()
                + intra_type_spread_deg * np.cos(angles) / lon_scale
            )
            out.loc[idx, "plot_lat"] = (
                out.loc[idx, "plot_lat"].to_numpy()
                + intra_type_spread_deg * np.sin(angles)
            )

    return out


def build_map(
    generators: pd.DataFrame,
    consumers: pd.DataFrame,
    lines: pd.DataFrame,
    hour_row: pd.Series,
    wind_scale: float,
    pv_scale: float,
    bess_scale: float,
    refs: dict[str, float],
) -> go.Figure:
    """Karte mit aktueller Stunde."""
    fig = go.Figure()

    total_gen = (
        hour_row["PV_GW"]
        + hour_row["Wind_GW"]
        + hour_row["Konv_GW"]
        + hour_row["BESS_Entladen_GW"]
    )
    load = float(hour_row["Last_GW"])
    fallback_factor = min(1.5, max(0.2, float(total_gen) / max(load, 1e-3)))

    if not lines.empty:
        for _, ln in lines.iterrows():
            if "Auslastung_pct" in lines.columns:
                util_pct = float(ln["Auslastung_pct"])
                util = util_pct / 100.0
                flow_proxy = float(ln.get("Flow_Proxy_GW", 0.0))
                overloaded = bool(ln.get("Ueberlast", False))
            else:
                util = min(1.0, fallback_factor * 0.6)
                util_pct = util * 100.0
                flow_proxy = 0.0
                overloaded = util_pct > 100.0

            if overloaded:
                color = "red"
            elif util_pct >= 90:
                color = "orange"
            else:
                color = "green"

            fig.add_trace(go.Scattergeo(
                lon=[ln["lon0"], ln["lon1"]],
                lat=[ln["lat0"], ln["lat1"]],
                mode="lines",
                line=dict(width=2 + 4 * min(util, 1.5), color=color),
                opacity=0.78,
                hoverinfo="text",
                text=(
                    f"{ln['Name']} ({ln['von']} -> {ln['nach']})<br>"
                    f"Kapazität: {ln['Kapazitaet_GW']:.2f} GW<br>"
                    f"Flow-Proxy: {flow_proxy:.2f} GW<br>"
                    f"Auslastung: {util_pct:.0f} %<br>"
                    f"Status: {'ÜBERLAST' if overloaded else 'ok'}"
                ),
                showlegend=False,
            ))

    typ_to_value = {
        "Wind": float(hour_row["Wind_GW"]),
        "PV": float(hour_row["PV_GW"]),
        "BESS": float(hour_row["BESS_GW"]),
        "Konventionell": float(hour_row["Konv_GW"]),
    }
    typ_to_inst = {
        "Wind": refs["wind_gw"] * wind_scale,
        "PV": refs["pv_gw"] * pv_scale,
        "BESS": refs["bess_gw"] * bess_scale,
        "Konventionell": refs["konv_gw"],
    }

    for typ in ["Wind", "PV", "BESS", "Konventionell"]:
        sub = generators[generators["Typ"] == typ].copy()
        if sub.empty:
            continue

        akt_total = typ_to_value[typ]
        inst_total = typ_to_inst[typ]
        sub["Aktuell_GW"] = sub["Anteil"] * akt_total
        sub["Installiert_GW"] = sub["Anteil"] * inst_total

        bus_values = sub["Bus"] if "Bus" in sub.columns else pd.Series(["-"] * len(sub))

        sub = apply_marker_offsets(sub)

        fig.add_trace(go.Scattergeo(
            lon=sub["plot_lon"],
            lat=sub["plot_lat"],
            text=[
                f"<b>{n}</b><br>Bus: {bus}<br>Typ: {typ}<br>"
                f"Aktuell: {a:.2f} GW<br>Installiert/Referenz: {i:.2f} GW<br>"
                f"Originalposition: {lat:.3f}, {lon:.3f}"
                for n, bus, a, i, lat, lon in zip(
                    sub["Name"],
                    bus_values,
                    sub["Aktuell_GW"],
                    sub["Installiert_GW"],
                    sub["lat"],
                    sub["lon"],
                )
            ],
            hoverinfo="text",
            mode="markers",
            name=typ,
            marker=dict(
                size=10 + np.abs(sub["Aktuell_GW"]) * 2.0,
                color=TYP_COLORS[typ],
                symbol=TYP_SYMBOLS[typ],
                line=dict(width=1, color="black"),
                opacity=0.9,
            ),
        ))

    cluster_load = consumers["Anteil"] * float(hour_row["Last_GW"])
    fig.add_trace(go.Scattergeo(
        lon=consumers["lon"],
        lat=consumers["lat"],
        text=[
            f"<b>{c}</b><br>Last aktuell: {l:.2f} GW"
            for c, l in zip(consumers["Cluster"], cluster_load)
        ],
        hoverinfo="text",
        mode="markers+text",
        name="Verbraucher-Cluster",
        textposition="top center",
        textfont=dict(size=11, color="black"),
        marker=dict(
            size=14 + cluster_load * 1.2,
            color=TYP_COLORS["Verbraucher"],
            symbol=TYP_SYMBOLS["Verbraucher"],
            line=dict(width=1.2, color="black"),
            opacity=0.9,
        ),
    ))

    fig.update_geos(
        visible=True,
        resolution=50,
        scope="europe",
        showcountries=True,
        countrycolor="black",
        showland=True,
        landcolor="rgb(240,240,235)",
        showocean=True,
        oceancolor="rgb(220,235,245)",
        lataxis_range=[47.0, 55.8],
        lonaxis_range=[5.0, 16.2],
    )

    fig.update_layout(
        height=620,
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=-0.05, x=0.5, xanchor="center"),
    )
    return fig


def build_stack(df: pd.DataFrame, highlight_hour: int) -> go.Figure:
    """Stack-Balkendiagramm für Last und Erzeugung."""
    h = df["Stunde"]
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=h, y=df["Konv_Grundlast_GW"], name="Konv. Grundlast",
        marker_color=TYP_COLORS["Konventionell"],
    ))
    fig.add_trace(go.Bar(
        x=h, y=df["Konv_Spitze_GW"], name="Konv. Spitze",
        marker_color="rgba(127,127,127,0.55)",
    ))
    fig.add_trace(go.Bar(
        x=h, y=df["Wind_GW"], name="Wind",
        marker_color=TYP_COLORS["Wind"],
    ))
    fig.add_trace(go.Bar(
        x=h, y=df["PV_GW"], name="PV",
        marker_color=TYP_COLORS["PV"],
    ))
    fig.add_trace(go.Bar(
        x=h, y=df["BESS_Entladen_GW"], name="BESS Entladen",
        marker_color=TYP_COLORS["BESS"],
    ))

    fig.add_trace(go.Bar(
        x=h, y=-df["BESS_Laden_GW"], name="BESS Laden",
        marker_color="rgba(44,160,44,0.5)",
    ))
    fig.add_trace(go.Bar(
        x=h, y=-df["Curtailment_GW"], name="Abregelung EE",
        marker_color="rgba(214,39,40,0.4)",
    ))

    fig.add_trace(go.Scatter(
        x=h, y=df["Last_GW"], name="Last",
        line=dict(color="black", width=3),
    ))

    fig.add_vline(x=highlight_hour, line_dash="dash", line_color="red")

    fig.update_layout(
        barmode="relative",
        title="Erzeugungsmix vs. Last - vereinfachter Dispatch",
        xaxis_title="Stunde",
        yaxis_title="Leistung [GW]",
        height=440,
        hovermode="x unified",
    )
    return fig


def build_line_utilization_chart(line_status: pd.DataFrame) -> go.Figure:
    """Balkendiagramm der Leitungs-Auslastung."""
    fig = go.Figure()

    if line_status.empty or "Auslastung_pct" not in line_status.columns:
        fig.update_layout(
            title="Keine Leitungsdaten verfügbar",
            height=320,
        )
        return fig

    sorted_lines = line_status.sort_values("Auslastung_pct", ascending=False)

    fig.add_trace(go.Bar(
        x=sorted_lines["Name"],
        y=sorted_lines["Auslastung_pct"],
        name="Auslastung",
        marker_color=[
            "red" if bool(x) else ("orange" if y >= 90 else "green")
            for x, y in zip(sorted_lines["Ueberlast"], sorted_lines["Auslastung_pct"])
        ],
        hovertext=[
            f"{row['Name']}<br>"
            f"{row['von']} → {row['nach']}<br>"
            f"Kapazität: {row['Kapazitaet_GW']:.2f} GW<br>"
            f"Flow-Proxy: {row['Flow_Proxy_GW']:.2f} GW<br>"
            f"Auslastung: {row['Auslastung_pct']:.0f} %"
            for _, row in sorted_lines.iterrows()
        ],
        hoverinfo="text",
    ))

    fig.add_hline(y=100, line_dash="dash", line_color="red")
    fig.update_layout(
        title="Leitungsauslastung - Proxy",
        xaxis_title="Leitung",
        yaxis_title="Auslastung [%]",
        height=380,
        margin=dict(l=40, r=20, t=50, b=120),
    )
    fig.update_xaxes(tickangle=-35)
    return fig


# =============================================================================
# Streamlit-App
# =============================================================================
def init_session_state() -> None:
    """Setzt robuste Default-Werte für alle interaktiven Stellgrößen."""
    if "scenario_key" not in st.session_state:
        st.session_state["scenario_key"] = "training"

    defaults = SCENARIOS["training"]["defaults"]
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def load_scenario_defaults(scenario_key: str) -> None:
    """Lädt die Startwerte eines Szenarios in den Session State."""
    scenario = SCENARIOS.get(scenario_key, SCENARIOS["training"])
    for key, value in scenario["defaults"].items():
        st.session_state[key] = value


def main() -> None:
    st.set_page_config(page_title="Deutschland-Netzkarte: Szenario-Modus", layout="wide")

    init_session_state()

    st.title("Deutschland-Netzkarte mit Szenario-Modus")
    st.markdown(
        """
        Diese App lädt ein PyPSA-Netz aus `simplified_germany_8node.nc` und nutzt daraus
        Busse, Leitungen/Links, Generatoren, Speicher und Lastverteilung.

        Aufgabe des Nutzers: ein Szenario so einstellen, dass weder Unterdeckung noch
        Überdeckung noch Leitungsüberlastung auftritt.

        Hinweis: Die Leitungsüberlastung ist ein didaktischer Proxy. Es wird kein echter
        AC/DC-Lastfluss gerechnet.
        """
    )

    try:
        n = load_pypsa_network(NETWORK_FILE)
        refs = get_reference_values(n)
        generators = pypsa_to_generators(n)
        consumers = pypsa_to_consumers(n)
        lines = pypsa_to_lines(n)
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    with st.sidebar:
        st.header("Szenario")

        scenario_key = st.selectbox(
            "Aufgabe",
            options=list(SCENARIOS.keys()),
            format_func=lambda k: SCENARIOS[k]["name"],
            key="scenario_key",
        )
        scenario = SCENARIOS[scenario_key]

        st.info(str(scenario["task"]))

        if st.button("Szenario-Startwerte laden"):
            load_scenario_defaults(scenario_key)
            st.rerun()

        st.header("Maßnahmen / Stellgrößen")

        wind_pct = st.slider("Wind [%]", 0, 300, key="wind_pct", step=5)
        pv_pct = st.slider("PV [%]", 0, 300, key="pv_pct", step=5)
        bess_pct = st.slider("BESS [%]", 0, 300, key="bess_pct", step=5)
        load_pct = st.slider("Last [%]", 50, 200, key="load_pct", step=5)
        soc_pct = st.slider("Start-SOC [%]", 0, 100, key="soc_pct", step=5)

        st.header("Netzmaßnahmen")
        line_capacity_pct = st.slider(
            "Leitungskapazität / Netzausbau [%]",
            50,
            200,
            key="line_capacity_pct",
            step=5,
        )
        ee_curtail_pct = st.slider(
            "EE-Abregelung [%]",
            0,
            80,
            key="ee_curtail_pct",
            step=5,
        )

        st.caption(
            f"Referenz aus Netz/Fallback:\n"
            f"- Wind = {refs['wind_gw']:.2f} GW\n"
            f"- PV = {refs['pv_gw']:.2f} GW\n"
            f"- BESS = {refs['bess_gw']:.2f} GW / {refs['bess_gwh']:.2f} GWh\n"
            f"- Konv. = {refs['konv_gw']:.2f} GW\n"
            f"- mittlere Last = {refs['load_mean_gw']:.2f} GW"
        )

        st.header("Konv. Grundlast")
        grundlast_anteil = st.slider(
            "Grundlast-Anteil der Last [%]", 10, 90, 55, 1
        ) / 100.0
        grundlast_min = st.slider(
            "Min. Betrieb (% der mittl. Last)", 0, 60, 30, 1
        ) / 100.0
        traegheit = st.slider(
            "Tragheit (klein = langsam)", 0.05, 1.0, 0.25, 0.05
        )

    wind_scale = wind_pct / 100.0
    pv_scale = pv_pct / 100.0
    bess_scale = bess_pct / 100.0
    load_scale = load_pct / 100.0

    profiles = generate_profiles(
        wind_scale=wind_scale,
        pv_scale=pv_scale,
        load_scale=load_scale,
        refs=refs,
    )

    profiles = apply_scenario_to_profiles(
        profiles,
        scenario_key=scenario_key,
        ee_curtail_pct=ee_curtail_pct,
    )

    df = simulate_dispatch(
        profiles,
        bess_scale=bess_scale,
        refs=refs,
        soc_start_pct=soc_pct,
        grundlast_anteil=grundlast_anteil,
        grundlast_min_anteil=grundlast_min,
        traegheit=traegheit,
    )

    st.subheader("Zeitslider")
    hour = st.slider("Stunde des Tages", 0, 23, key="hour", step=1)
    hour_row = df.iloc[hour]

    line_status = compute_line_status_proxy(
        generators=generators,
        consumers=consumers,
        lines=lines,
        hour_row=hour_row,
        line_capacity_pct=line_capacity_pct,
        line_stress_factor=float(SCENARIOS[scenario_key]["line_stress_factor"]),
    )

    scenario_eval = evaluate_scenario(
        hour_row=hour_row,
        line_status=line_status,
        scenario_key=scenario_key,
    )

    # -------------------------------------------------------------------------
    # Live-Kennzahlen
    # -------------------------------------------------------------------------
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Last [GW]", f"{hour_row['Last_GW']:.2f}")
    k2.metric("Wind [GW]", f"{hour_row['Wind_GW']:.2f}")
    k3.metric("PV [GW]", f"{hour_row['PV_GW']:.2f}")
    k4.metric("BESS [GW]", f"{hour_row['BESS_GW']:+.2f}")
    k5.metric("Konv. [GW]", f"{hour_row['Konv_GW']:.2f}")

    k6, k7, k8 = st.columns(3)
    k6.metric("Netzbilanz [GW]", f"{hour_row['Netzbilanz_GW']:+.2f}")
    k7.metric("SOC [%]", f"{hour_row['SOC_pct']:.1f}")
    k8.metric("Dispatch-Status", str(hour_row["Status"]))

    # -------------------------------------------------------------------------
    # Szenario-Bewertung
    # -------------------------------------------------------------------------
    st.subheader("Szenario-Bewertung")

    if scenario_eval["solved"]:
        st.success("Szenario bewältigt.")
    else:
        st.warning("Szenario noch nicht bewältigt.")

    for msg in scenario_eval["messages"]:
        st.write(f"- {msg}")

    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Bilanz [GW]", f"{scenario_eval['balance_gw']:+.2f}")
    b2.metric("Abregelung [GW]", f"{scenario_eval['curtailment_gw']:.2f}")
    b3.metric("max. Leitung [%]", f"{scenario_eval['peak_line_util_pct']:.0f}")
    b4.metric("überlastete Leitungen", str(scenario_eval["overloaded_count"]))

    with st.expander("Zielbedingungen"):
        st.write(
            "- Netzbilanz zwischen -1 GW und +1 GW\n"
            "- Abregelung unter Szenario-Grenzwert\n"
            "- keine Leitung über 100 % Auslastung\n"
            "- Leitungswerte sind Proxy-Werte, kein echter Lastfluss"
        )

    # -------------------------------------------------------------------------
    # Visualisierungen
    # -------------------------------------------------------------------------
    st.subheader("Netzkarte")
    fig_map = build_map(
        generators=generators,
        consumers=consumers,
        lines=line_status,
        hour_row=hour_row,
        wind_scale=wind_scale,
        pv_scale=pv_scale,
        bess_scale=bess_scale,
        refs=refs,
    )
    st.plotly_chart(fig_map, use_container_width=True)

    st.subheader("Leitungsauslastung")
    fig_line = build_line_utilization_chart(line_status)
    st.plotly_chart(fig_line, use_container_width=True)

    st.subheader("Erzeugungsmix vs. Last über 24 h")
    fig_stack = build_stack(df, highlight_hour=hour)
    st.plotly_chart(fig_stack, use_container_width=True)

    # -------------------------------------------------------------------------
    # Tabellen
    # -------------------------------------------------------------------------
    with st.expander("Stündliche Tabelle"):
        st.dataframe(
            df[[
                "Stunde", "Last_GW", "PV_GW", "Wind_GW",
                "Konv_Grundlast_GW", "Konv_Spitze_GW", "Konv_GW",
                "BESS_GW", "Curtailment_GW", "SOC_GWh", "SOC_pct",
                "Netzbilanz_GW", "Status",
            ]].round(3),
            use_container_width=True,
        )

    with st.expander("PyPSA-Busse / Verbraucher-Cluster"):
        st.dataframe(consumers.round(4), use_container_width=True)

    with st.expander("PyPSA-Erzeuger"):
        st.dataframe(generators.round(4), use_container_width=True)

    with st.expander("PyPSA-Leitungen und Links mit Auslastung"):
        st.dataframe(line_status.round(4), use_container_width=True)

    with st.expander("Netz-Referenzwerte"):
        st.json(refs)

    st.caption(
        "Die Topologie kommt aus der NetCDF-Datei. Profile, Dispatch, BESS-Logik "
        "und Leitungsauslastung sind didaktische Proxys. Es wird kein AC/DC-Lastfluss "
        "und keine PyPSA-Optimierung berechnet."
    )


if __name__ == "__main__":
    main()
