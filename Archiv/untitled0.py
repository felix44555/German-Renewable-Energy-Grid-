from pathlib import Path

scenario_tools = r'''from __future__ import annotations

import numpy as np
import pandas as pd


SCENARIOS: dict[str, dict[str, object]] = {
    "training": {
        "name": "Freies Training",
        "task": (
            "Keine feste Störung. Ziel: Netzbilanz nahe 0 GW halten und "
            "Leitungsüberlastungen vermeiden."
        ),
        "defaults": {
            "wind_pct": 100,
            "pv_pct": 100,
            "bess_pct": 100,
            "load_pct": 100,
            "soc_pct": 50,
            "hour": 12,
            "line_capacity_pct": 100,
            "ee_curtail_pct": 0,
        },
        "wind_profile_factor": 1.0,
        "pv_profile_factor": 1.0,
        "load_event_boost": 0.0,
        "load_event_hour": 19,
        "load_event_width": 4.0,
        "line_stress_factor": 1.0,
        "max_abs_balance_gw": 1.0,
        "max_curtailment_gw": 1.0,
        "max_line_util_pct": 100.0,
    },
    "unterdeckung": {
        "name": "Szenario 1: Dunkelflaute + Abendspitze",
        "task": (
            "Es herrscht wenig Wind und PV, gleichzeitig steigt abends die Last. "
            "Der Nutzer muss Unterdeckung vermeiden."
        ),
        "defaults": {
            "wind_pct": 35,
            "pv_pct": 50,
            "bess_pct": 50,
            "load_pct": 160,
            "soc_pct": 20,
            "hour": 19,
            "line_capacity_pct": 100,
            "ee_curtail_pct": 0,
        },
        "wind_profile_factor": 0.35,
        "pv_profile_factor": 0.75,
        "load_event_boost": 0.18,
        "load_event_hour": 19,
        "load_event_width": 3.0,
        "line_stress_factor": 1.0,
        "max_abs_balance_gw": 1.0,
        "max_curtailment_gw": 1.0,
        "max_line_util_pct": 100.0,
    },
    "ueberschuss": {
        "name": "Szenario 2: PV-Überschuss am Mittag",
        "task": (
            "Starke PV-Einspeisung trifft auf geringe Last. "
            "Der Nutzer muss Überdeckung und unnötige Abregelung begrenzen."
        ),
        "defaults": {
            "wind_pct": 120,
            "pv_pct": 280,
            "bess_pct": 40,
            "load_pct": 65,
            "soc_pct": 85,
            "hour": 13,
            "line_capacity_pct": 100,
            "ee_curtail_pct": 0,
        },
        "wind_profile_factor": 1.0,
        "pv_profile_factor": 1.20,
        "load_event_boost": -0.12,
        "load_event_hour": 13,
        "load_event_width": 4.0,
        "line_stress_factor": 1.1,
        "max_abs_balance_gw": 1.0,
        "max_curtailment_gw": 1.0,
        "max_line_util_pct": 100.0,
    },
    "leitung": {
        "name": "Szenario 3: Nord-Süd-Engpass",
        "task": (
            "Hohe Windleistung im Norden/Osten und hohe Last im Süden/Westen "
            "belasten die Übertragungsleitungen. Der Nutzer muss Leitungsüberlastung vermeiden."
        ),
        "defaults": {
            "wind_pct": 260,
            "pv_pct": 80,
            "bess_pct": 60,
            "load_pct": 135,
            "soc_pct": 45,
            "hour": 18,
            "line_capacity_pct": 65,
            "ee_curtail_pct": 0,
        },
        "wind_profile_factor": 1.35,
        "pv_profile_factor": 0.85,
        "load_event_boost": 0.08,
        "load_event_hour": 18,
        "load_event_width": 5.0,
        "line_stress_factor": 1.85,
        "max_abs_balance_gw": 1.0,
        "max_curtailment_gw": 2.0,
        "max_line_util_pct": 100.0,
    },
}


def apply_scenario_to_profiles(
    df: pd.DataFrame,
    scenario_key: str,
    ee_curtail_pct: float = 0.0,
) -> pd.DataFrame:
    """
    Verändert die 24-h-Profile durch eine didaktische Störung.

    ee_curtail_pct ist eine vom Nutzer gewählte Maßnahme:
    0 % = keine vorsorgliche Abregelung,
    100 % = Wind und PV vollständig abgeregelt.
    """
    sc = SCENARIOS.get(scenario_key, SCENARIOS["training"])
    out = df.copy()

    out["Wind_GW"] *= float(sc.get("wind_profile_factor", 1.0))
    out["PV_GW"] *= float(sc.get("pv_profile_factor", 1.0))

    boost = float(sc.get("load_event_boost", 0.0))
    if abs(boost) > 1e-12:
        h0 = float(sc.get("load_event_hour", 19))
        width = max(float(sc.get("load_event_width", 4.0)), 0.5)
        h = out["Stunde"].astype(float).to_numpy()
        shape = np.exp(-((h - h0) ** 2) / width)
        out["Last_GW"] *= 1.0 + boost * shape

    curtail_factor = 1.0 - np.clip(float(ee_curtail_pct), 0.0, 100.0) / 100.0
    out["Wind_GW"] *= curtail_factor
    out["PV_GW"] *= curtail_factor

    return out


def _nearest_consumer_bus(lat: float, lon: float, consumers: pd.DataFrame) -> str:
    """
    Ordnet Generatoren ohne explizite Bus-Spalte dem nächsten Verbraucher-/Bus-Knoten zu.
    Das ist nur ein didaktischer Proxy, kein Lastfluss.
    """
    if consumers.empty:
        return ""

    lat_arr = pd.to_numeric(consumers["lat"], errors="coerce").to_numpy(dtype=float)
    lon_arr = pd.to_numeric(consumers["lon"], errors="coerce").to_numpy(dtype=float)
    d2 = (lat_arr - float(lat)) ** 2 + ((lon_arr - float(lon)) * 0.65) ** 2
    idx = int(np.nanargmin(d2))

    if "Bus" in consumers.columns:
        return str(consumers.iloc[idx]["Bus"])
    return str(consumers.iloc[idx]["Cluster"])


def compute_bus_balance_proxy(
    generators: pd.DataFrame,
    consumers: pd.DataFrame,
    hour_row: pd.Series,
) -> pd.Series:
    """
    Näherung der Knoteneinspeisung in GW:
    positiv = Einspeisung, negativ = Last.

    Verwendet die bestehenden App-DataFrames. Falls Generatoren keine Bus-Spalte haben,
    werden sie geografisch dem nächsten Verbraucher-/Bus-Knoten zugeordnet.
    """
    if consumers.empty:
        return pd.Series(dtype=float)

    bus_col = "Bus" if "Bus" in consumers.columns else "Cluster"
    buses = consumers[bus_col].astype(str).tolist()
    balance = pd.Series(0.0, index=buses, dtype=float)

    # Last je Bus abziehen
    for _, row in consumers.iterrows():
        bus = str(row[bus_col])
        balance.loc[bus] -= float(row["Anteil"]) * float(hour_row["Last_GW"])

    # Erzeugung je Typ auf Standorte verteilen
    type_power = {
        "Wind": float(hour_row.get("Wind_GW", 0.0)),
        "PV": float(hour_row.get("PV_GW", 0.0)),
        "Konventionell": float(hour_row.get("Konv_GW", 0.0)),
        # BESS_GW > 0: Entladung; BESS_GW < 0: Ladung als zusätzliche Last
        "BESS": float(hour_row.get("BESS_GW", 0.0)),
    }

    for _, row in generators.iterrows():
        typ = str(row["Typ"])
        if typ not in type_power:
            continue

        if "Bus" in generators.columns and pd.notna(row.get("Bus", None)):
            bus = str(row["Bus"])
        else:
            bus = _nearest_consumer_bus(float(row["lat"]), float(row["lon"]), consumers)

        if bus not in balance.index:
            bus = _nearest_consumer_bus(float(row["lat"]), float(row["lon"]), consumers)

        if bus in balance.index:
            balance.loc[bus] += float(row["Anteil"]) * type_power[typ]

    return balance


def compute_line_status_proxy(
    generators: pd.DataFrame,
    consumers: pd.DataFrame,
    lines: pd.DataFrame,
    hour_row: pd.Series,
    line_capacity_pct: float = 100.0,
    line_stress_factor: float = 1.0,
) -> pd.DataFrame:
    """
    Erzeugt eine didaktische Leitungs-Auslastung.

    Wichtig: Das ist KEIN AC/DC-Lastfluss. Es ist ein Proxy aus
    Knoteneinspeisung, lokaler Leistungsdifferenz und Leitungskapazität.
    """
    if lines.empty:
        return lines.copy()

    out = lines.copy()
    balance = compute_bus_balance_proxy(generators, consumers, hour_row)

    cap_scale = max(float(line_capacity_pct), 1.0) / 100.0
    stress = max(float(line_stress_factor), 0.1)

    positive_caps = pd.to_numeric(out["Kapazitaet_GW"], errors="coerce")
    positive_caps = positive_caps[positive_caps > 0]
    fallback_cap = float(positive_caps.median()) if not positive_caps.empty else 1.0
    fallback_cap = max(fallback_cap, 0.5)

    max_lat_span = max(float((out["lat0"] - out["lat1"]).abs().max()), 0.5)
    system_imbalance = abs(float(hour_row.get("Netzbilanz_GW", 0.0)))

    flows = []
    utils = []
    overloads = []

    for _, ln in out.iterrows():
        bus0 = str(ln["von"])
        bus1 = str(ln["nach"])

        # Falls von/nach nicht exakt Bus-Namen sind, geografisch auf nächsten Bus mappen.
        if bus0 not in balance.index:
            bus0 = _nearest_consumer_bus(float(ln["lat0"]), float(ln["lon0"]), consumers)
        if bus1 not in balance.index:
            bus1 = _nearest_consumer_bus(float(ln["lat1"]), float(ln["lon1"]), consumers)

        p0 = float(balance.get(bus0, 0.0))
        p1 = float(balance.get(bus1, 0.0))

        cap = float(ln.get("Kapazitaet_GW", 0.0))
        if not np.isfinite(cap) or cap <= 0:
            cap = fallback_cap
        cap *= cap_scale

        local_pressure = abs(p0 - p1)
        ns_factor = 1.0 + 0.65 * abs(float(ln["lat0"]) - float(ln["lat1"])) / max_lat_span

        # Skalierung bewusst konservativ, damit Überlast erst bei Stressszenarien sichtbar wird.
        flow = stress * ns_factor * (0.32 * local_pressure + 0.05 * system_imbalance)
        util_pct = 100.0 * flow / max(cap, 1e-6)

        flows.append(flow)
        utils.append(util_pct)
        overloads.append(util_pct > 100.0)

    out["Flow_Proxy_GW"] = flows
    out["Auslastung_pct"] = utils
    out["Ueberlast"] = overloads
    return out


def evaluate_scenario(
    hour_row: pd.Series,
    line_status: pd.DataFrame,
    scenario_key: str,
) -> dict[str, object]:
    """Bewertet, ob der Nutzer das gewählte Szenario beherrscht."""
    sc = SCENARIOS.get(scenario_key, SCENARIOS["training"])

    max_abs_balance = float(sc.get("max_abs_balance_gw", 1.0))
    max_curtail = float(sc.get("max_curtailment_gw", 1.0))
    max_line_util = float(sc.get("max_line_util_pct", 100.0))

    balance = float(hour_row.get("Netzbilanz_GW", 0.0))
    curtail = float(hour_row.get("Curtailment_GW", 0.0))

    if line_status.empty or "Auslastung_pct" not in line_status.columns:
        peak_line_util = 0.0
        overloaded_count = 0
        worst_line = "-"
    else:
        peak_line_util = float(line_status["Auslastung_pct"].max())
        overloaded_count = int((line_status["Auslastung_pct"] > max_line_util).sum())
        worst_idx = line_status["Auslastung_pct"].idxmax()
        worst_line = str(line_status.loc[worst_idx, "Name"])

    under = balance < -max_abs_balance
    over = balance > max_abs_balance or curtail > max_curtail
    line_over = peak_line_util > max_line_util

    messages: list[str] = []
    if under:
        messages.append(f"Unterdeckung: Netzbilanz {balance:+.2f} GW.")
    if over:
        if balance > max_abs_balance:
            messages.append(f"Überdeckung: Netzbilanz {balance:+.2f} GW.")
        if curtail > max_curtail:
            messages.append(f"Abregelung zu hoch: {curtail:.2f} GW.")
    if line_over:
        messages.append(
            f"Leitungsüberlastung: {worst_line} bei {peak_line_util:.0f} %."
        )

    solved = not under and not over and not line_over

    if solved:
        messages.append("Szenario bewältigt: Bilanz stabil und keine Leitungsüberlastung.")

    return {
        "solved": solved,
        "under": under,
        "over": over,
        "line_over": line_over,
        "balance_gw": balance,
        "curtailment_gw": curtail,
        "peak_line_util_pct": peak_line_util,
        "overloaded_count": overloaded_count,
        "worst_line": worst_line,
        "messages": messages,
    }
'''

path = Path("/mnt/data/scenario_tools.py")
path.write_text(scenario_tools, encoding="utf-8")
path
