from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import importlib
import math
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    import pypsa
except ImportError:  # pragma: no cover
    pypsa = None

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

# =============================================================================
# Konfiguration
# =============================================================================
BASE_DIR = Path(__file__).resolve().parent
NETWORK_FILE = BASE_DIR / "real_germany_8n.nc"

APP_TZ = "Europe/Berlin"
HOURS = np.arange(24)
SMARD_BASE_URL = "https://www.smard.de/app/chart_data"
SMARD_REGION = "DE"
SMARD_RESOLUTION = "hour"

# SMARD ist in diesem Modell nur Orientierungsquelle für Last, Wind und PV.
# Importe/Exporte und restliche Erzeuger werden bewusst nicht geladen.
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

FALLBACK_REFS = {
    "wind_gw": 70.0,
    "pv_gw": 90.0,
    "konv_gw": 80.0,
    "bess_gw": 12.0,
    "bess_gwh": 24.0,
    "load_mean_gw": 60.0,
}

# =============================================================================
# Szenario-Integration
# =============================================================================
REQUIRED_SCENARIO_SYMBOLS = (
    "SCENARIOS",
    "apply_scenario_to_profiles",
    "compute_line_status_proxy",
    "evaluate_scenario",
)

LOCAL_SCENARIOS: dict[str, dict[str, Any]] = {
    "training": {
        "name": "Training: SMARD-Orientierung",
        "task": (
            "Nutze Wind, PV, restliche Erzeuger, BESS, Last und Abregelung so, "
            "dass die SMARD-Netzlast ohne Importe/Exporte bilanziell gedeckt wird. "
            "Restliche Erzeuger sind eine künstlich regelbare Stellgröße und nicht an SMARD gekoppelt."
        ),
        "defaults": {
            "wind_pct": 100,
            "pv_pct": 100,
            "konv_pct": 100,
            "konv_min_pct": 0,
            "bess_pct": 100,
            "load_pct": 100,
            "soc_pct": 50,
            "line_capacity_pct": 100,
            "ee_curtail_pct": 0,
            "hour": 12,
        },
        "profile_factors": {"wind": 1.00, "pv": 1.00, "load": 1.00},
        "line_stress_factor": 1.00,
        "limits": {"balance_abs_gw": 1.0, "max_curtailment_gw": 6.0, "max_line_util_pct": 100.0},
    },
    "unterdeckung": {
        "name": "Unterdeckung: Restleistung reicht nicht",
        "task": (
            "Wind/PV sind niedrig und die Last ist hoch. Die restlichen Erzeuger fahren bis zur verfügbaren "
            "Leistung hoch; verbleibende Unterdeckung muss durch BESS, Lastsenkung oder höhere Verfügbarkeit gelöst werden."
        ),
        "defaults": {
            "wind_pct": 70,
            "pv_pct": 65,
            "konv_pct": 70,
            "konv_min_pct": 0,
            "bess_pct": 100,
            "load_pct": 115,
            "soc_pct": 75,
            "line_capacity_pct": 100,
            "ee_curtail_pct": 0,
            "hour": 19,
        },
        "profile_factors": {"wind": 0.75, "pv": 0.75, "load": 1.08},
        "line_stress_factor": 1.05,
        "limits": {"balance_abs_gw": 1.0, "max_curtailment_gw": 3.0, "max_line_util_pct": 100.0},
    },
    "ueberschuss": {
        "name": "Überdeckung: EE hoch, Rest runterfahren",
        "task": (
            "Hohe Wind- und PV-Leistung trifft auf geringe Last. Fahre restliche Erzeuger herunter, lade BESS "
            "oder regle EE ab, ohne zu viel Curtailment zu erzeugen."
        ),
        "defaults": {
            "wind_pct": 145,
            "pv_pct": 160,
            "konv_pct": 100,
            "konv_min_pct": 15,
            "bess_pct": 120,
            "load_pct": 85,
            "soc_pct": 30,
            "line_capacity_pct": 100,
            "ee_curtail_pct": 0,
            "hour": 13,
        },
        "profile_factors": {"wind": 1.15, "pv": 1.25, "load": 0.90},
        "line_stress_factor": 1.10,
        "limits": {"balance_abs_gw": 1.0, "max_curtailment_gw": 8.0, "max_line_util_pct": 100.0},
    },
    "leitungsueberlast": {
        "name": "Leitungsüberlast: Nord-Süd-Transport",
        "task": (
            "Hoher Windanteil erzeugt räumliche Überschüsse. Löse Bilanz und Leitungsauslastung über "
            "Netzausbau, BESS, Abregelung oder veränderte verfügbare Restleistung."
        ),
        "defaults": {
            "wind_pct": 170,
            "pv_pct": 100,
            "konv_pct": 90,
            "konv_min_pct": 5,
            "bess_pct": 100,
            "load_pct": 100,
            "soc_pct": 50,
            "line_capacity_pct": 70,
            "ee_curtail_pct": 0,
            "hour": 21,
        },
        "profile_factors": {"wind": 1.35, "pv": 0.95, "load": 1.00},
        "line_stress_factor": 1.55,
        "limits": {"balance_abs_gw": 1.0, "max_curtailment_gw": 6.0, "max_line_util_pct": 100.0},
    },
}


def _scenario_module_is_valid(module: ModuleType) -> bool:
    return all(hasattr(module, name) for name in REQUIRED_SCENARIO_SYMBOLS)


def _load_external_scenarios() -> tuple[dict[str, dict[str, Any]], Any, Any, Any, str]:
    candidates = ("scenarios", "szenarien", "scenario_tools")
    errors: list[str] = []

    for module_name in candidates:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            errors.append(f"{module_name}: {exc}")
            continue

        if _scenario_module_is_valid(module):
            scenarios = getattr(module, "SCENARIOS")
            if isinstance(scenarios, dict) and "training" in scenarios:
                return (
                    scenarios,
                    getattr(module, "apply_scenario_to_profiles"),
                    getattr(module, "compute_line_status_proxy"),
                    getattr(module, "evaluate_scenario"),
                    f"extern: {module_name}.py",
                )
            errors.append(f"{module_name}: SCENARIOS fehlt oder enthält kein 'training'")
        else:
            missing = [name for name in REQUIRED_SCENARIO_SYMBOLS if not hasattr(module, name)]
            errors.append(f"{module_name}: fehlende Symbole {missing}")

    return (
        LOCAL_SCENARIOS,
        _local_apply_scenario_to_profiles,
        _local_compute_line_status_proxy,
        _local_evaluate_scenario,
        "lokaler Fallback in app.py (" + " | ".join(errors) + ")",
    )


def _local_apply_scenario_to_profiles(
    profiles: pd.DataFrame,
    scenario_key: str,
    ee_curtail_pct: float = 0.0,
) -> pd.DataFrame:
    """Szenariofaktoren wirken nur auf SMARD-orientierte Größen: Last, Wind, PV."""
    scenario = LOCAL_SCENARIOS.get(scenario_key, LOCAL_SCENARIOS["training"])
    factors = scenario.get("profile_factors", {})
    out = profiles.copy()

    for col, key in (("Wind_GW", "wind"), ("PV_GW", "pv"), ("Last_GW", "load")):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0) * float(factors.get(key, 1.0))

    # EE-Abregelung wird im Dispatch angewendet. Diese Spalte hält nur Vorab-Abregelung aus externen Szenarien kompatibel.
    out["Pre_Curtailment_GW"] = 0.0
    if ee_curtail_pct:
        curtail_frac = float(np.clip(ee_curtail_pct, 0.0, 100.0)) / 100.0
        old_ee = out.get("Wind_GW", 0.0) + out.get("PV_GW", 0.0)
        if "Wind_GW" in out.columns:
            out["Wind_GW"] *= 1.0 - curtail_frac
        if "PV_GW" in out.columns:
            out["PV_GW"] *= 1.0 - curtail_frac
        new_ee = out.get("Wind_GW", 0.0) + out.get("PV_GW", 0.0)
        out["Pre_Curtailment_GW"] = old_ee - new_ee

    return out


def _as_float(value: object, default: float = 0.0) -> float:
    """Robuste Float-Konvertierung für PyPSA-/DataFrame-Werte."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(out):
        return default
    return out


def _line_reactance_ohm(row: pd.Series) -> float:
    """
    Liefert eine positive Serienreaktanz in Ohm.

    PyPSA-Netze enthalten bei AC-Leitungen normalerweise `x`. In manchen
    reduzierten/aggregierten Netzen steht dort 0.0. Für DC-Lastfluss darf x
    nicht 0 sein; dann wird aus Leitungslänge und parallelen Systemen ein
    plausibler Ersatzwert abgeleitet.
    """
    x = _as_float(row.get("X_Ohm", row.get("x", np.nan)), np.nan)
    if np.isfinite(x) and abs(x) > 1e-9:
        return abs(x)

    length_km = _as_float(row.get("Laenge_km", row.get("length", 0.0)), 0.0)
    num_parallel = max(_as_float(row.get("Num_parallel", row.get("num_parallel", 1.0)), 1.0), 1e-6)
    v_nom = _as_float(row.get("V_nom_kV", row.get("v_nom", 380.0)), 380.0)

    # Typische Serienreaktanz von Höchstspannungs-Freileitungen. Der Wert ist
    # bewusst konservativ; er verhindert unendliche Flüsse bei x=0-Datensätzen.
    typical_x_ohm_per_km = 0.30 if v_nom >= 300.0 else 0.40
    if length_km > 0.0:
        return typical_x_ohm_per_km * length_km / num_parallel

    # Letzter Fallback aus thermischer Kapazität und einem zulässigen Winkel von
    # ca. 20 Grad. Nicht ideal, aber stabil und transparent.
    cap_gw = _as_float(row.get("Kapazitaet_GW", 0.0), 0.0)
    if cap_gw > 0.0 and v_nom > 0.0:
        max_angle_rad = np.deg2rad(20.0)
        return (v_nom**2) / max(cap_gw * 1000.0 / max_angle_rad, 1e-9)

    return 1.0


def _branch_susceptance_gw_per_rad(row: pd.Series) -> float:
    """
    DC-Suszeptanz b in GW/rad aus U^2 / X.

    Für eine verlustlose AC-Leitung gilt im DC-Lastfluss näherungsweise:
        P_ij = b_ij * (theta_i - theta_j)
    mit b_ij = U_nom^2 / X. Bei U in kV und X in Ohm ergibt das MW/rad;
    geteilt durch 1000 ergibt GW/rad.
    """
    x_ohm = max(_line_reactance_ohm(row), 1e-9)
    v_nom = max(_as_float(row.get("V_nom_kV", 380.0), 380.0), 1.0)
    return (v_nom**2) / x_ohm / 1000.0


def _compute_nodal_injections_gw(
    generators: pd.DataFrame,
    consumers: pd.DataFrame,
    buses: list[str],
    hour_row: pd.Series,
) -> pd.DataFrame:
    """Baut die Knoteneinspeisungen P_i in GW: Erzeugung positiv, Last negativ."""
    nodal = pd.DataFrame(index=pd.Index(buses, name="Bus"))
    for col in ("Wind_GW", "PV_GW", "Konv_GW", "BESS_GW", "Last_GW"):
        nodal[col] = 0.0

    typ_to_col = {
        "Wind": "Wind_GW",
        "PV": "PV_GW",
        "Konventionell": "Konv_GW",
        "BESS": "BESS_GW",
    }
    typ_power = {typ: _as_float(hour_row.get(col, 0.0), 0.0) for typ, col in typ_to_col.items()}

    if not generators.empty and "Bus" in generators.columns:
        for _, gen in generators.iterrows():
            bus = str(gen.get("Bus", ""))
            typ = str(gen.get("Typ", ""))
            if bus not in nodal.index or typ not in typ_to_col:
                continue
            share = _as_float(gen.get("Anteil", 0.0), 0.0)
            nodal.loc[bus, typ_to_col[typ]] += share * typ_power[typ]

    total_load = _as_float(hour_row.get("Last_GW", 0.0), 0.0)
    if not consumers.empty and "Bus" in consumers.columns:
        for _, load in consumers.iterrows():
            bus = str(load.get("Bus", ""))
            if bus not in nodal.index:
                continue
            share = _as_float(load.get("Anteil", 0.0), 0.0)
            nodal.loc[bus, "Last_GW"] += share * total_load

    nodal["P_vor_Slack_GW"] = (
        nodal["Wind_GW"]
        + nodal["PV_GW"]
        + nodal["Konv_GW"]
        + nodal["BESS_GW"]
        - nodal["Last_GW"]
    )
    nodal["Slack_Ausgleich_GW"] = 0.0
    nodal["P_nach_Slack_GW"] = nodal["P_vor_Slack_GW"]
    nodal["Theta_rad"] = 0.0
    nodal["Theta_grad"] = 0.0
    return nodal


def _connected_components(n_buses: int, branches: list[tuple[int, int, float]]) -> list[list[int]]:
    adjacency: list[list[int]] = [[] for _ in range(n_buses)]
    for i, j, b in branches:
        if b <= 0.0:
            continue
        adjacency[i].append(j)
        adjacency[j].append(i)

    seen = [False] * n_buses
    comps: list[list[int]] = []
    for start in range(n_buses):
        if seen[start]:
            continue
        stack = [start]
        seen[start] = True
        comp: list[int] = []
        while stack:
            node = stack.pop()
            comp.append(node)
            for nbr in adjacency[node]:
                if not seen[nbr]:
                    seen[nbr] = True
                    stack.append(nbr)
        comps.append(sorted(comp))
    return comps


def _choose_component_slack(component: list[int], bus_names: list[str], nodal: pd.DataFrame) -> int:
    """Slack je Netzinsel: bevorzugt größter absoluter Last-/Erzeugungsknoten."""
    if not component:
        return 0
    scores = []
    for idx in component:
        bus = bus_names[idx]
        row = nodal.loc[bus]
        score = abs(_as_float(row.get("Last_GW", 0.0), 0.0)) + abs(_as_float(row.get("Konv_GW", 0.0), 0.0))
        scores.append((score, idx))
    return max(scores)[1]


def _solve_dc_angles(
    bus_names: list[str],
    branches: list[tuple[int, int, float]],
    nodal: pd.DataFrame,
) -> tuple[np.ndarray, pd.DataFrame]:
    """
    Löst B_bus * theta = P je zusammenhängender Netzinsel.

    Jede Insel erhält einen eigenen Slack-Bus. Dadurch bleibt die Rechnung auch
    bei unvollständigen oder reduzierten Netzen numerisch stabil.

    Wichtig: Die Knoteneinspeisungen werden absichtlich als Python-Liste geführt.
    Einige Streamlit/Pandas-Kombinationen liefern aus DataFrame-Spalten Arrays,
    die nicht sicher in-place beschreibbar sind. Dadurch kann `p[slack] -= ...`
    als ValueError abbrechen. Die Listenvariante vermeidet diesen Fehler robust.
    """
    n_buses = len(bus_names)
    bbus = np.zeros((n_buses, n_buses), dtype=float)
    for i, j, b in branches:
        if b <= 0.0:
            continue
        bbus[i, i] += b
        bbus[j, j] += b
        bbus[i, j] -= b
        bbus[j, i] -= b

    theta = np.zeros(n_buses, dtype=float)
    p: list[float] = (
        pd.to_numeric(nodal["P_nach_Slack_GW"], errors="coerce")
        .fillna(0.0)
        .astype(float)
        .tolist()
    )

    for comp in _connected_components(n_buses, branches):
        if len(comp) <= 1:
            slack = comp[0]
            imbalance = float(p[slack])
            p[slack] = float(p[slack]) - imbalance
            nodal.loc[bus_names[slack], "Slack_Ausgleich_GW"] -= imbalance
            nodal.loc[bus_names[slack], "P_nach_Slack_GW"] = float(p[slack])
            continue

        slack = _choose_component_slack(comp, bus_names, nodal)
        imbalance = float(sum(p[idx] for idx in comp))
        p[slack] = float(p[slack]) - imbalance
        nodal.loc[bus_names[slack], "Slack_Ausgleich_GW"] -= imbalance
        nodal.loc[bus_names[slack], "P_nach_Slack_GW"] = float(p[slack])

        active = [idx for idx in comp if idx != slack]
        bred = bbus[np.ix_(active, active)]
        pred = np.array([p[idx] for idx in active], dtype=float)
        try:
            theta_active = np.linalg.solve(bred, pred)
        except np.linalg.LinAlgError:
            theta_active = np.linalg.pinv(bred) @ pred
        theta[active] = theta_active
        theta[slack] = 0.0

    nodal["Theta_rad"] = theta
    nodal["Theta_grad"] = np.rad2deg(theta)
    return theta, nodal


def _local_compute_line_status_proxy(
    generators: pd.DataFrame,
    consumers: pd.DataFrame,
    lines: pd.DataFrame,
    hour_row: pd.Series,
    line_capacity_pct: float,
    line_stress_factor: float = 1.0,
) -> pd.DataFrame:
    """
    Berechnet eine DC-Lastfluss-Näherung für die App.

    Annahmen:
    - AC-Leitungen werden verlustlos und rein reaktiv modelliert.
    - Spannungshöhen sind konstant; nur Winkel werden gelöst.
    - BESS_GW ist positiv bei Entladung und negativ bei Ladung.
    - Eine nicht ausgeglichene globale Bilanz wird pro Netzinsel über einen
      Slack-Bus ausgeglichen, damit der lineare Lastfluss lösbar ist.
    """
    if lines.empty:
        return lines.copy()

    out = lines.copy()
    buses = sorted(
        set(out["von"].astype(str))
        .union(set(out["nach"].astype(str)))
        .union(set(generators.get("Bus", pd.Series(dtype=str)).astype(str)))
        .union(set(consumers.get("Bus", pd.Series(dtype=str)).astype(str)))
    )
    bus_to_idx = {bus: idx for idx, bus in enumerate(buses)}

    nodal = _compute_nodal_injections_gw(generators, consumers, buses, hour_row)

    branches: list[tuple[int, int, float]] = []
    b_values: list[float] = []
    x_values: list[float] = []
    for _, ln in out.iterrows():
        bus0 = str(ln.get("von", ""))
        bus1 = str(ln.get("nach", ""))
        b = _branch_susceptance_gw_per_rad(ln)
        x = _line_reactance_ohm(ln)
        b_values.append(b)
        x_values.append(x)
        branches.append((bus_to_idx[bus0], bus_to_idx[bus1], b))

    theta, nodal = _solve_dc_angles(buses, branches, nodal)

    cap_factor = float(np.clip(line_capacity_pct, 1.0, 500.0)) / 100.0
    stress = max(float(line_stress_factor), 0.0)

    raw_flows: list[float] = []
    signed_flows: list[float] = []
    abs_flows: list[float] = []
    util_values: list[float] = []
    overload_flags: list[bool] = []
    effective_caps: list[float] = []
    theta0_values: list[float] = []
    theta1_values: list[float] = []
    delta_theta_values: list[float] = []

    for (_, ln), b, x_ohm in zip(out.iterrows(), b_values, x_values):
        bus0 = str(ln.get("von", ""))
        bus1 = str(ln.get("nach", ""))
        i = bus_to_idx[bus0]
        j = bus_to_idx[bus1]
        delta_theta = float(theta[i] - theta[j])
        raw_flow = b * delta_theta
        signed_flow = raw_flow * stress
        abs_flow = abs(signed_flow)

        raw_cap = _as_float(ln.get("Kapazitaet_GW", 0.0), 0.0)
        effective_cap = max(raw_cap * cap_factor, 0.30)
        util_pct = 100.0 * abs_flow / effective_cap

        raw_flows.append(raw_flow)
        signed_flows.append(signed_flow)
        abs_flows.append(abs_flow)
        util_values.append(util_pct)
        overload_flags.append(util_pct > 100.0)
        effective_caps.append(effective_cap)
        theta0_values.append(float(theta[i]))
        theta1_values.append(float(theta[j]))
        delta_theta_values.append(delta_theta)

    out["X_eff_Ohm"] = x_values
    out["B_DC_GW_pro_rad"] = b_values
    out["Effektive_Kapazitaet_GW"] = effective_caps
    out["Theta_von_rad"] = theta0_values
    out["Theta_nach_rad"] = theta1_values
    out["Delta_Theta_rad"] = delta_theta_values
    out["Flow_DC_Roh_GW"] = raw_flows
    out["Flow_DC_GW"] = signed_flows
    out["Flow_Abs_GW"] = abs_flows
    # Kompatibilitätsalias für bestehende Diagramme/ externe Auswertung.
    out["Flow_Proxy_GW"] = abs_flows
    out["Auslastung_pct"] = util_values
    out["Ueberlast"] = overload_flags
    out["Slack_Busse"] = ", ".join(nodal.index[nodal["Slack_Ausgleich_GW"].abs() > 1e-9].astype(str).tolist())
    out["Globaler_Slack_Ausgleich_GW"] = float(nodal["Slack_Ausgleich_GW"].sum())
    out["Netzbilanz_vor_Slack_GW"] = float(nodal["P_vor_Slack_GW"].sum())
    out["Szenario_Flow_Faktor"] = stress

    nodal = nodal.reset_index()
    nodal["Ist_Slack"] = nodal["Slack_Ausgleich_GW"].abs() > 1e-9
    out.attrs["dc_nodal_status"] = nodal
    out.attrs["dc_model_note"] = (
        "DC-Lastfluss: P_ij = b_ij * (theta_i - theta_j), "
        "verlustlos, konstante Spannung, Slack-Ausgleich je Netzinsel."
    )
    return out


def _local_evaluate_scenario(hour_row: pd.Series, line_status: pd.DataFrame, scenario_key: str) -> dict[str, Any]:
    scenario = LOCAL_SCENARIOS.get(scenario_key, LOCAL_SCENARIOS["training"])
    limits = scenario.get("limits", {})
    balance_limit = float(limits.get("balance_abs_gw", 1.0))
    curtail_limit = float(limits.get("max_curtailment_gw", 6.0))
    line_limit = float(limits.get("max_line_util_pct", 100.0))

    balance = float(hour_row.get("Netzbilanz_GW", 0.0))
    curtailment = float(hour_row.get("Curtailment_GW", 0.0))

    if line_status.empty or "Auslastung_pct" not in line_status.columns:
        peak_line = 0.0
        overloaded_count = 0
    else:
        util = pd.to_numeric(line_status["Auslastung_pct"], errors="coerce").fillna(0.0)
        peak_line = float(util.max())
        overloaded_count = int((util > line_limit).sum())

    messages: list[str] = []
    if abs(balance) <= balance_limit:
        messages.append(f"Bilanz ok: {balance:+.2f} GW innerhalb ±{balance_limit:.1f} GW.")
    elif balance < -balance_limit:
        messages.append(f"Unterdeckung: {balance:+.2f} GW. Mehr verfügbare Restleistung, BESS-Entladung oder Lastsenkung nötig.")
    else:
        messages.append(f"Überdeckung: {balance:+.2f} GW. Restleistung senken, BESS laden, EE abregeln oder Last erhöhen.")

    if curtailment <= curtail_limit:
        messages.append(f"Abregelung ok: {curtailment:.2f} GW ≤ {curtail_limit:.2f} GW.")
    else:
        messages.append(f"Abregelung zu hoch: {curtailment:.2f} GW > {curtail_limit:.2f} GW.")

    if overloaded_count == 0:
        messages.append(f"Leitungen ok: maximale Auslastung {peak_line:.0f} %.")
    else:
        messages.append(f"Leitungsüberlast: {overloaded_count} Leitung(en), Maximum {peak_line:.0f} %.")

    solved = abs(balance) <= balance_limit and curtailment <= curtail_limit and overloaded_count == 0
    return {
        "solved": solved,
        "messages": messages,
        "balance_gw": balance,
        "curtailment_gw": curtailment,
        "peak_line_util_pct": peak_line,
        "overloaded_count": overloaded_count,
    }


SCENARIOS, apply_scenario_to_profiles, _external_compute_line_status_proxy, evaluate_scenario, SCENARIO_SOURCE = _load_external_scenarios()

# Szenarien/Evaluierung dürfen extern kommen; die Leitungsauslastung wird immer
# mit der internen DC-Lastfluss-Näherung berechnet, nicht mit einem alten Proxy.
compute_line_status_proxy = _local_compute_line_status_proxy
SCENARIO_SOURCE = f"{SCENARIO_SOURCE}; Leitungen: interner DC-Lastfluss"

# =============================================================================
# SMARD API: nur Last, Wind, PV
# =============================================================================
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


@st.cache_data(ttl=3600, show_spinner=False)
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


@st.cache_data(ttl=3600, show_spinner=False)
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


@st.cache_data(ttl=3600, show_spinner="Lade SMARD-Orientierungsdaten ...")
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
        # Nicht aus SMARD. Wird im Dispatch künstlich gesetzt.
        "Konv_GW": np.zeros(24, dtype=float),
        "BESS_GW": np.zeros(24, dtype=float),
    })
    profile["SMARD_EE_Orientierung_GW"] = profile["Wind_GW"] + profile["PV_GW"]
    profile["SMARD_Zielluecke_GW"] = profile["Last_GW"] - profile["SMARD_EE_Orientierung_GW"]
    profile["timestamp"] = pd.to_datetime(day_iso) + pd.to_timedelta(profile["Stunde"], unit="h")

    return profile, pd.DataFrame(meta_rows)

# =============================================================================
# PyPSA -> App-Datenmodell
# =============================================================================
@st.cache_resource(show_spinner=False)
def load_pypsa_network(path_str: str, mtime_ns: int):
    if pypsa is None:
        raise RuntimeError("PyPSA ist nicht installiert. Ergänze 'pypsa' in requirements.txt.")
    path = Path(path_str)
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


def _require_bus_coordinates(n) -> None:
    if "x" not in n.buses.columns or "y" not in n.buses.columns:
        raise ValueError("Die PyPSA-Busse brauchen Koordinaten: n.buses.x und n.buses.y.")
    missing = n.buses[["x", "y"]].isna().any(axis=1)
    if bool(missing.any()):
        bad = ", ".join(map(str, n.buses.index[missing].tolist()))
        raise ValueError(f"Folgende Busse haben fehlende Koordinaten: {bad}")


def _load_by_bus_mw(n) -> pd.Series:
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


def pypsa_to_consumers(n) -> pd.DataFrame:
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


def pypsa_to_lines(n) -> pd.DataFrame:
    """Konvertiert PyPSA-Lines und Links zu Kartenleitungen inklusive DC-Parameter."""
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
                "X_Ohm": _as_float(ln.get("x", np.nan), np.nan),
                "R_Ohm": _as_float(ln.get("r", np.nan), np.nan),
                "B_Siemens": _as_float(ln.get("b", np.nan), np.nan),
                "V_nom_kV": _as_float(ln.get("v_nom", 380.0), 380.0),
                "Laenge_km": _as_float(ln.get("length", np.nan), np.nan),
                "Num_parallel": _as_float(ln.get("num_parallel", 1.0), 1.0),
            })

    # Links werden bei Bedarf als steuerbare DC-Zweige mit kapazitätsbasiertem
    # Ersatz-X modelliert. In deiner 8-Knoten-Datei sind aktuell keine Links nötig.
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

    return pd.DataFrame(rows, columns=[
        "Name", "Typ", "von", "nach", "lat0", "lon0", "lat1", "lon1",
        "Kapazitaet_GW", "X_Ohm", "R_Ohm", "B_Siemens", "V_nom_kV",
        "Laenge_km", "Num_parallel",
    ])


def pypsa_to_generators(n) -> pd.DataFrame:
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


def get_reference_values(n) -> dict[str, float]:
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

# =============================================================================
# Profile und Dispatch
# =============================================================================
def generate_synthetic_profiles(refs: dict[str, float], seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    h = HOURS
    raw_load_shape = (
        55.0
        + 12.0 * np.exp(-((h - 8) ** 2) / 6.0)
        + 8.0 * np.exp(-((h - 13) ** 2) / 10.0)
        + 18.0 * np.exp(-((h - 19) ** 2) / 5.0)
    )
    load_shape = raw_load_shape / float(np.mean(raw_load_shape))
    load = refs["load_mean_gw"] * load_shape

    pv_shape = np.where((h >= 6) & (h <= 20), np.exp(-((h - 13) ** 2) / 9.0), 0.0)
    pv = refs["pv_gw"] * 0.55 * pv_shape

    raw_wind = rng.normal(loc=0.45, scale=0.18, size=24)
    wind_factor = np.convolve(raw_wind, np.ones(5) / 5.0, mode="same")
    wind_factor = np.clip(wind_factor, 0.08, 0.85)
    wind = refs["wind_gw"] * wind_factor

    out = pd.DataFrame({"Stunde": h, "Last_GW": load, "Wind_GW": wind, "PV_GW": pv})
    out["Konv_GW"] = 0.0
    out["BESS_GW"] = 0.0
    out["SMARD_EE_Orientierung_GW"] = out["Wind_GW"] + out["PV_GW"]
    out["SMARD_Zielluecke_GW"] = out["Last_GW"] - out["SMARD_EE_Orientierung_GW"]
    return out


def prepare_dispatch_profiles(
    profiles: pd.DataFrame,
    wind_scale: float,
    pv_scale: float,
    konv_scale: float,
    load_scale: float,
    bess_scale: float,
    refs: dict[str, float],
    soc_start_pct: float,
    ee_curtail_pct: float,
    konv_min_pct: float = 0.0,
    eta: float = 0.90,
) -> pd.DataFrame:
    """
    Dispatch-Modell:
    - SMARD liefert nur Last, Wind und PV als Orientierung.
    - Restliche Erzeuger sind nicht SMARD-gekoppelt.
    - Konv_GW wird künstlich auf die Residuallast gefahren, begrenzt durch .nc-/Fallback-Kapazität.
    - BESS gleicht danach verbleibende Unter-/Überdeckung aus.
    """
    out = profiles.copy()
    for col in ("Wind_GW", "PV_GW", "Last_GW"):
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    out["Wind_GW"] *= wind_scale
    out["PV_GW"] *= pv_scale
    out["Last_GW"] *= load_scale

    # EE-Abregelung nach Skalierung.
    curtail_frac = float(np.clip(ee_curtail_pct, 0.0, 100.0)) / 100.0
    ee_before = out["Wind_GW"] + out["PV_GW"]
    out["Wind_GW"] *= 1.0 - curtail_frac
    out["PV_GW"] *= 1.0 - curtail_frac
    out["Curtailment_GW"] = ee_before - (out["Wind_GW"] + out["PV_GW"])
    if "Pre_Curtailment_GW" in out.columns:
        out["Curtailment_GW"] += pd.to_numeric(out["Pre_Curtailment_GW"], errors="coerce").fillna(0.0)

    # Restliche Erzeuger als künstlich regelbare Leistung.
    konv_max = max(float(refs["konv_gw"]) * float(konv_scale), 0.0)
    konv_min = konv_max * float(np.clip(konv_min_pct, 0.0, 100.0)) / 100.0
    residual_after_ee = out["Last_GW"] - out["Wind_GW"] - out["PV_GW"]

    out["Konv_Soll_GW"] = residual_after_ee
    out["Konv_Min_GW"] = konv_min
    out["Konv_Max_GW"] = konv_max
    out["Konv_GW"] = np.clip(residual_after_ee, konv_min, konv_max)
    out["Konv_Fehlleistung_GW"] = np.maximum(residual_after_ee - konv_max, 0.0)
    out["Konv_Mindestlauf_Ueberschuss_GW"] = np.maximum(konv_min - residual_after_ee, 0.0)

    p_bess_max = max(float(refs["bess_gw"]) * float(bess_scale), 0.0)
    cap_bess = max(float(refs["bess_gwh"]) * float(bess_scale), 0.0)
    soc = cap_bess * float(np.clip(soc_start_pct, 0.0, 100.0)) / 100.0
    soc_min = 0.10 * cap_bess
    soc_max = 0.95 * cap_bess

    bess_p: list[float] = []
    soc_track: list[float] = []
    status: list[str] = []
    balance_before: list[float] = []
    residual_before: list[float] = []

    for _, row in out.iterrows():
        load = float(row["Last_GW"])
        domestic = float(row["Wind_GW"] + row["PV_GW"] + row["Konv_GW"])
        residual = load - domestic
        residual_before.append(residual)
        balance_before.append(domestic - load)

        b_power = 0.0
        if cap_bess > 0 and p_bess_max > 0:
            if residual > 1e-9:
                discharge_power = min(residual, p_bess_max)
                energy_taken = discharge_power / eta
                if soc - energy_taken < soc_min:
                    energy_taken = max(soc - soc_min, 0.0)
                    discharge_power = energy_taken * eta
                soc -= energy_taken
                b_power = discharge_power
            elif residual < -1e-9:
                charge_power = min(-residual, p_bess_max)
                energy_stored = charge_power * eta
                if soc + energy_stored > soc_max:
                    energy_stored = max(soc_max - soc, 0.0)
                    charge_power = energy_stored / eta if eta > 0 else 0.0
                soc += energy_stored
                b_power = -charge_power

        nb = domestic + b_power - load
        if nb < -1.0:
            stat = "Unterdeckung"
        elif nb > 1.0:
            stat = "Ueberschuss"
        elif float(row.get("Curtailment_GW", 0.0)) > 0.5:
            stat = "Abregelung"
        else:
            stat = "stabil"

        bess_p.append(b_power)
        soc_track.append(soc)
        status.append(stat)

    out["BESS_GW"] = bess_p
    out["BESS_Laden_GW"] = [max(-x, 0.0) for x in bess_p]
    out["BESS_Entladen_GW"] = [max(x, 0.0) for x in bess_p]
    out["SOC_GWh"] = soc_track
    out["SOC_pct"] = [s / cap_bess * 100.0 if cap_bess > 0 else 0.0 for s in soc_track]
    out["Bilanz_vor_BESS_GW"] = balance_before
    out["Zielluecke_vor_BESS_GW"] = residual_before
    out["Inlaendische_Erzeugung_GW"] = out["Wind_GW"] + out["PV_GW"] + out["Konv_GW"]
    out["Netzbilanz_GW"] = out["Inlaendische_Erzeugung_GW"] + out["BESS_GW"] - out["Last_GW"]
    out["Status"] = status
    return out

# =============================================================================
# Visualisierung
# =============================================================================
TYP_COLORS = {
    "Wind": "#1f77b4",
    "PV": "#ff7f0e",
    "BESS": "#2ca02c",
    "Konventionell": "#7f7f7f",
    "Import/Export": "#9467bd",
    "Lastabwurf": "#8c564b",
    "Verbraucher": "#d62728",
}

TYP_SYMBOLS = {
    "Wind": "triangle-up",
    "PV": "square",
    "BESS": "diamond",
    "Konventionell": "circle",
    "Import/Export": "x",
    "Lastabwurf": "cross",
    "Verbraucher": "star",
}

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
    out = df.copy()
    if out.empty:
        out["plot_lon"] = []
        out["plot_lat"] = []
        return out

    out["plot_lon"] = pd.to_numeric(out[lon_col], errors="coerce").astype(float)
    out["plot_lat"] = pd.to_numeric(out[lat_col], errors="coerce").astype(float)

    for typ, (dx, dy) in MARKER_OFFSET_DIRECTIONS.items():
        mask = out[typ_col] == typ
        if not bool(mask.any()):
            continue
        lat_rad = np.deg2rad(out.loc[mask, lat_col].astype(float))
        lon_scale = np.maximum(np.cos(lat_rad), 0.35)
        out.loc[mask, "plot_lon"] = out.loc[mask, lon_col].astype(float) + dx * offset_deg / lon_scale
        out.loc[mask, "plot_lat"] = out.loc[mask, lat_col].astype(float) + dy * offset_deg

    if bus_col in out.columns:
        for _, idx in out.groupby([bus_col, typ_col], sort=False).groups.items():
            idx = list(idx)
            if len(idx) <= 1:
                continue
            angles = np.linspace(0.0, 2.0 * np.pi, len(idx), endpoint=False)
            lat_rad = np.deg2rad(out.loc[idx, lat_col].astype(float))
            lon_scale = np.maximum(np.cos(lat_rad), 0.35)
            out.loc[idx, "plot_lon"] = out.loc[idx, "plot_lon"].to_numpy() + intra_type_spread_deg * np.cos(angles) / lon_scale
            out.loc[idx, "plot_lat"] = out.loc[idx, "plot_lat"].to_numpy() + intra_type_spread_deg * np.sin(angles)

    return out


def build_map(
    generators: pd.DataFrame,
    consumers: pd.DataFrame,
    lines: pd.DataFrame,
    hour_row: pd.Series,
    wind_scale: float,
    pv_scale: float,
    konv_scale: float,
    bess_scale: float,
    refs: dict[str, float],
) -> go.Figure:
    fig = go.Figure()

    if not lines.empty:
        for _, ln in lines.iterrows():
            util_pct = float(ln.get("Auslastung_pct", 0.0))
            util = util_pct / 100.0
            flow_dc = float(ln.get("Flow_DC_GW", ln.get("Flow_Proxy_GW", 0.0)))
            overloaded = bool(ln.get("Ueberlast", False))
            color = "red" if overloaded else ("orange" if util_pct >= 90 else "green")
            fig.add_trace(go.Scattergeo(
                lon=[ln["lon0"], ln["lon1"]],
                lat=[ln["lat0"], ln["lat1"]],
                mode="lines",
                line=dict(width=2 + 4 * min(util, 1.5), color=color),
                opacity=0.78,
                hoverinfo="text",
                text=(
                    f"{ln['Name']} ({ln['von']} → {ln['nach']})<br>"
                    f"Kapazität: {float(ln['Kapazitaet_GW']):.2f} GW<br>"
                    f"DC-Flow: {flow_dc:+.2f} GW<br>"
                    f"Auslastung: {util_pct:.0f} %<br>"
                    f"Status: {'ÜBERLAST' if overloaded else 'ok'}"
                ),
                showlegend=False,
            ))

    typ_to_value = {
        "Wind": float(hour_row.get("Wind_GW", 0.0)),
        "PV": float(hour_row.get("PV_GW", 0.0)),
        "BESS": float(hour_row.get("BESS_GW", 0.0)),
        "Konventionell": float(hour_row.get("Konv_GW", 0.0)),
    }
    typ_to_inst = {
        "Wind": refs["wind_gw"] * wind_scale,
        "PV": refs["pv_gw"] * pv_scale,
        "BESS": refs["bess_gw"] * bess_scale,
        "Konventionell": refs["konv_gw"] * konv_scale,
    }

    for typ in ["Wind", "PV", "BESS", "Konventionell"]:
        sub = generators[generators["Typ"] == typ].copy()
        if sub.empty:
            continue
        sub["Aktuell_GW"] = sub["Anteil"] * typ_to_value[typ]
        sub["Installiert_GW"] = sub["Anteil"] * typ_to_inst[typ]
        sub = apply_marker_offsets(sub)
        marker_size = 10 + np.sqrt(np.maximum(np.abs(sub["Aktuell_GW"]), 0.0)) * 4.0
        fig.add_trace(go.Scattergeo(
            lon=sub["plot_lon"],
            lat=sub["plot_lat"],
            text=[
                f"<b>{n}</b><br>Bus: {bus}<br>Typ: {typ}<br>"
                f"Aktuell: {a:.2f} GW<br>Referenz/Skaliert: {i:.2f} GW<br>"
                f"Originalposition: {lat:.3f}, {lon:.3f}"
                for n, bus, a, i, lat, lon in zip(
                    sub["Name"], sub["Bus"], sub["Aktuell_GW"], sub["Installiert_GW"], sub["lat"], sub["lon"]
                )
            ],
            hoverinfo="text",
            mode="markers",
            name=typ,
            marker=dict(
                size=marker_size,
                color=TYP_COLORS[typ],
                symbol=TYP_SYMBOLS[typ],
                line=dict(width=1, color="black"),
                opacity=0.9,
            ),
        ))

    if not consumers.empty:
        cluster_load = consumers["Anteil"] * float(hour_row.get("Last_GW", 0.0))
        fig.add_trace(go.Scattergeo(
            lon=consumers["lon"],
            lat=consumers["lat"],
            text=[f"<b>{c}</b><br>Last aktuell: {l:.2f} GW" for c, l in zip(consumers["Cluster"], cluster_load)],
            hoverinfo="text",
            mode="markers+text",
            name="Verbraucher-Cluster",
            textposition="top center",
            textfont=dict(size=11, color="black"),
            marker=dict(
                size=14 + np.sqrt(np.maximum(cluster_load, 0.0)) * 5.0,
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
    h = df["Stunde"]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=h, y=df["Konv_GW"], name="Restliche Erzeuger geregelt", marker_color=TYP_COLORS["Konventionell"]))
    fig.add_trace(go.Bar(x=h, y=df["Wind_GW"], name="Wind", marker_color=TYP_COLORS["Wind"]))
    fig.add_trace(go.Bar(x=h, y=df["PV_GW"], name="PV", marker_color=TYP_COLORS["PV"]))
    fig.add_trace(go.Bar(x=h, y=df["BESS_Entladen_GW"], name="BESS Entladen", marker_color=TYP_COLORS["BESS"]))
    fig.add_trace(go.Bar(x=h, y=-df["BESS_Laden_GW"], name="BESS Laden", marker_color="rgba(44,160,44,0.5)"))
    fig.add_trace(go.Bar(x=h, y=-df["Curtailment_GW"], name="EE-Abregelung", marker_color="rgba(214,39,40,0.4)"))
    fig.add_trace(go.Scatter(x=h, y=df["Last_GW"], name="Last/Ziel", line=dict(color="black", width=3)))
    fig.add_trace(go.Scatter(x=h, y=df["Konv_Soll_GW"], name="Soll Restl. Erz. vor Limits", line=dict(color="gray", width=2, dash="dot")))
    fig.add_vline(x=highlight_hour, line_dash="dash", line_color="red")
    fig.update_layout(
        barmode="relative",
        title="Dispatch: SMARD-Last/Wind/PV + künstlich geregelte restliche Erzeuger",
        xaxis_title="Stunde",
        yaxis_title="Leistung [GW]",
        height=440,
        hovermode="x unified",
    )
    return fig


def build_balance_chart(df: pd.DataFrame, highlight_hour: int) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df["Stunde"], y=df["Bilanz_vor_BESS_GW"], name="Bilanz vor BESS"))
    fig.add_trace(go.Scatter(x=df["Stunde"], y=df["Netzbilanz_GW"], name="Bilanz nach BESS", line=dict(width=3)))
    fig.add_hline(y=0, line_color="black", line_width=1)
    fig.add_hline(y=1, line_dash="dash", line_color="red")
    fig.add_hline(y=-1, line_dash="dash", line_color="red")
    fig.add_vline(x=highlight_hour, line_dash="dash", line_color="red")
    fig.update_layout(
        title="Ziellücke / Netzbilanz ohne externe Importe und Exporte",
        xaxis_title="Stunde",
        yaxis_title="GW",
        height=340,
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
            f"DC-Flow: {row.get('Flow_DC_GW', row.get('Flow_Proxy_GW', 0.0)):+.2f} GW<br>"
            f"Auslastung: {row['Auslastung_pct']:.0f} %"
            for _, row in sorted_lines.iterrows()
        ],
        hoverinfo="text",
    ))

    fig.add_hline(y=100, line_dash="dash", line_color="red")
    fig.update_layout(
        title="Leitungsauslastung - DC-Lastfluss",
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
    if "scenario_key" not in st.session_state:
        st.session_state["scenario_key"] = "training"

    scenario = SCENARIOS.get("training", LOCAL_SCENARIOS["training"])
    defaults = dict(scenario.get("defaults", {}))
    fallback_defaults = LOCAL_SCENARIOS["training"]["defaults"]
    for key, value in fallback_defaults.items():
        defaults.setdefault(key, value)
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def load_scenario_defaults(scenario_key: str) -> None:
    scenario = SCENARIOS.get(scenario_key, SCENARIOS.get("training", LOCAL_SCENARIOS["training"]))
    defaults = dict(LOCAL_SCENARIOS.get(scenario_key, LOCAL_SCENARIOS["training"]).get("defaults", {}))
    defaults.update(scenario.get("defaults", {}))
    for key, value in defaults.items():
        st.session_state[key] = value


def _safe_scenario_line_stress(scenario_key: str) -> float:
    scenario = SCENARIOS.get(scenario_key, SCENARIOS.get("training", LOCAL_SCENARIOS["training"]))
    return float(scenario.get("line_stress_factor", 1.0))


def _format_gap(value: float) -> str:
    if value > 0:
        return f"Unterdeckung {value:.2f} GW"
    if value < 0:
        return f"Überdeckung {abs(value):.2f} GW"
    return "ausgeglichen"


def main() -> None:
    st.set_page_config(page_title="Deutschland-Netzkarte: SMARD + regelbare Restleistung", layout="wide")
    init_session_state()

    st.title("Deutschland-Netzkarte: SMARD-Orientierung und regelbare Restleistung")
    st.markdown(
        "SMARD wird nur für Netzlast, Wind und PV genutzt. Externe Importe/Exporte und SMARD-Restkategorien "
        "werden nicht geladen. Die restlichen Erzeuger werden künstlich als regelbare Leistung aus der .nc-/Fallback-Kapazität modelliert."
    )
    st.caption(
        "Version: DC-Lastfluss-SAFE-2. BESS ist eine vereinfachte Speicher-Stellgröße. Leitungsauslastung wird mit einer DC-Lastfluss-Näherung gerechnet. "
        f"Szenarioquelle: {SCENARIO_SOURCE}"
    )

    try:
        if not NETWORK_FILE.exists():
            raise FileNotFoundError(f"Netzdatei nicht gefunden: {NETWORK_FILE.name}")
        n = load_pypsa_network(str(NETWORK_FILE), NETWORK_FILE.stat().st_mtime_ns)
        refs = get_reference_values(n)
        consumers = pypsa_to_consumers(n)
        generators = ensure_bess_visible(pypsa_to_generators(n), consumers)
        lines = pypsa_to_lines(n)
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    with st.sidebar:
        st.header("Szenario")
        scenario_key = st.selectbox(
            "Aufgabe",
            options=list(SCENARIOS.keys()),
            format_func=lambda k: SCENARIOS[k].get("name", k),
            key="scenario_key",
        )
        scenario = SCENARIOS[scenario_key]
        st.info(str(scenario.get("task", "")))
        if st.button("Szenario-Startwerte laden"):
            load_scenario_defaults(scenario_key)
            st.rerun()

        st.header("Datenquelle")
        profile_source = st.radio(
            "Zeitreihe",
            options=["SMARD-API", "synthetisch"],
            index=0,
            help="SMARD lädt nur Netzlast, Wind Offshore/Onshore und PV. Restliche Erzeuger kommen nicht aus SMARD.",
        )
        default_day = date.today() - timedelta(days=2)
        smard_day = st.date_input(
            "SMARD-Datum",
            value=default_day,
            min_value=date(2018, 10, 1),
            max_value=date.today(),
            help="Sehr aktuelle Tage können noch unvollständige SMARD-Daten haben.",
        )
        region = st.selectbox("SMARD-Region", options=["DE", "50Hertz", "Amprion", "TenneT", "TransnetBW"], index=0)

        st.header("Stellgrößen")
        wind_pct = st.slider("Wind [% der SMARD-Orientierung]", 0, 300, key="wind_pct", step=5)
        pv_pct = st.slider("PV [% der SMARD-Orientierung]", 0, 300, key="pv_pct", step=5)
        konv_pct = st.slider(
            "Restliche Erzeuger verfügbare Leistung [%]",
            0,
            250,
            key="konv_pct",
            step=5,
            help="Skaliert die verfügbare regelbare Leistung aus .nc/Fallback. Nicht SMARD-gekoppelt.",
        )
        konv_min_pct = st.slider(
            "Restliche Erzeuger Mindestbetrieb [% verfügbar]",
            0,
            80,
            key="konv_min_pct",
            step=5,
            help="0 % bedeutet vollständig herunterfahrbar. Höhere Werte erzeugen bei viel EE eher Überschuss.",
        )
        bess_pct = st.slider("BESS Leistung/Energie [%]", 0, 300, key="bess_pct", step=5)
        load_pct = st.slider("Last/Ziel [% der SMARD-Last]", 50, 200, key="load_pct", step=5)
        soc_pct = st.slider("BESS Start-SOC [%]", 0, 100, key="soc_pct", step=5)

        st.header("Netz- und EE-Maßnahmen")
        line_capacity_pct = st.slider("Leitungskapazität / Netzausbau [%]", 50, 200, key="line_capacity_pct", step=5)
        ee_curtail_pct = st.slider("EE-Abregelung [% von Wind+PV]", 0, 80, key="ee_curtail_pct", step=5)

        st.caption(
            f"Referenzwerte aus Netz/Fallback:\n"
            f"- Wind: {refs['wind_gw']:.2f} GW\n"
            f"- PV: {refs['pv_gw']:.2f} GW\n"
            f"- Restliche Erzeuger: {refs['konv_gw']:.2f} GW\n"
            f"- BESS: {refs['bess_gw']:.2f} GW / {refs['bess_gwh']:.2f} GWh\n"
            f"- mittlere Netzlast: {refs['load_mean_gw']:.2f} GW"
        )

    wind_scale = wind_pct / 100.0
    pv_scale = pv_pct / 100.0
    konv_scale = konv_pct / 100.0
    bess_scale = bess_pct / 100.0
    load_scale = load_pct / 100.0

    api_meta = pd.DataFrame()
    if profile_source == "SMARD-API":
        try:
            base_profiles, api_meta = load_smard_api_profile(smard_day.isoformat(), region=region)
        except Exception as exc:
            st.error(f"SMARD-API-Daten konnten nicht geladen werden: {exc}")
            st.info("Prüfe Internetzugang, Datum und requirements.txt. Für Offline-Demo kann die synthetische Quelle genutzt werden.")
            st.stop()
    else:
        base_profiles = generate_synthetic_profiles(refs)

    try:
        scenario_profiles = apply_scenario_to_profiles(base_profiles, scenario_key=scenario_key, ee_curtail_pct=0.0)
    except Exception:
        scenario_profiles = _local_apply_scenario_to_profiles(base_profiles, scenario_key=scenario_key, ee_curtail_pct=0.0)

    df = prepare_dispatch_profiles(
        scenario_profiles,
        wind_scale=wind_scale,
        pv_scale=pv_scale,
        konv_scale=konv_scale,
        load_scale=load_scale,
        bess_scale=bess_scale,
        refs=refs,
        soc_start_pct=soc_pct,
        ee_curtail_pct=ee_curtail_pct,
        konv_min_pct=konv_min_pct,
    )

    st.subheader("Zeitslider")
    hour = st.slider("Stunde des Tages", 0, 23, key="hour", step=1)
    hour_row = df.iloc[int(hour)]

    line_status = compute_line_status_proxy(
        generators=generators,
        consumers=consumers,
        lines=lines,
        hour_row=hour_row,
        line_capacity_pct=line_capacity_pct,
        line_stress_factor=_safe_scenario_line_stress(scenario_key),
    )

    scenario_eval = evaluate_scenario(hour_row=hour_row, line_status=line_status, scenario_key=scenario_key)

    st.subheader("Live-Kennzahlen")
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Last/Ziel [GW]", f"{hour_row['Last_GW']:.2f}")
    k2.metric("Wind [GW]", f"{hour_row['Wind_GW']:.2f}")
    k3.metric("PV [GW]", f"{hour_row['PV_GW']:.2f}")
    k4.metric("Restl. Erz. [GW]", f"{hour_row['Konv_GW']:.2f}")
    k5.metric("BESS [GW]", f"{hour_row['BESS_GW']:+.2f}")
    k6.metric("Bilanz [GW]", f"{hour_row['Netzbilanz_GW']:+.2f}")

    b1, b2, b3, b4, b5 = st.columns(5)
    b1.metric("Ziellücke nach EE", _format_gap(float(hour_row["Last_GW"] - hour_row["Wind_GW"] - hour_row["PV_GW"])))
    b2.metric("Restl. Soll [GW]", f"{hour_row['Konv_Soll_GW']:.2f}")
    b3.metric("Restl. verfügbar [GW]", f"{hour_row['Konv_Max_GW']:.2f}")
    b4.metric("Ziellücke vor BESS", _format_gap(float(hour_row["Zielluecke_vor_BESS_GW"])))
    b5.metric("SOC [%]", f"{hour_row['SOC_pct']:.1f}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Konv. Fehlleistung", f"{hour_row['Konv_Fehlleistung_GW']:.2f} GW")
    c2.metric("Mindestlauf-Überschuss", f"{hour_row['Konv_Mindestlauf_Ueberschuss_GW']:.2f} GW")
    c3.metric("Abregelung", f"{hour_row['Curtailment_GW']:.2f} GW")
    c4.metric("Status", str(hour_row["Status"]))

    st.subheader("Szenario-Bewertung")
    if bool(scenario_eval.get("solved", False)):
        st.success("Szenario bewältigt.")
    else:
        st.warning("Szenario noch nicht bewältigt.")

    for msg in scenario_eval.get("messages", []):
        st.write(f"- {msg}")

    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Bilanz [GW]", f"{scenario_eval.get('balance_gw', 0.0):+.2f}")
    e2.metric("Abregelung [GW]", f"{scenario_eval.get('curtailment_gw', 0.0):.2f}")
    e3.metric("max. Leitung [%]", f"{scenario_eval.get('peak_line_util_pct', 0.0):.0f}")
    e4.metric("überlastete Leitungen", str(scenario_eval.get("overloaded_count", 0)))

    with st.expander("Modellannahmen"):
        st.write(
            "- Zielgröße ist die SMARD-Netzlast.\n"
            "- Wind = SMARD Wind Offshore + Wind Onshore.\n"
            "- PV = SMARD Photovoltaik.\n"
            "- Restliche Erzeuger werden nicht aus SMARD geladen, sondern künstlich auf die Residuallast gefahren.\n"
            "- Externe Importe, Exporte und kommerzielle Austauschflüsse werden nicht geladen.\n"
            "- Import-/Export- und Lastabwurf-Carrier aus der .nc zählen nicht als konventionelle Referenzleistung.\n"
            "- BESS: positiv = Entladung, negativ = Ladung.\n"
            "- Leitungsauslastung wird per DC-Lastfluss-Näherung mit Slack-Bus berechnet."
        )

    c_left, c_right = st.columns([1.2, 1.0])
    with c_left:
        st.subheader("Netzkarte")
        st.plotly_chart(
            build_map(
                generators=generators,
                consumers=consumers,
                lines=line_status,
                hour_row=hour_row,
                wind_scale=wind_scale,
                pv_scale=pv_scale,
                konv_scale=konv_scale,
                bess_scale=bess_scale,
                refs=refs,
            ),
            use_container_width=True,
        )
    with c_right:
        st.subheader("Leitungsauslastung")
        st.plotly_chart(build_line_utilization_chart(line_status), use_container_width=True)

    st.subheader("Bilanz und Erzeugungsmix")
    st.plotly_chart(build_balance_chart(df, highlight_hour=int(hour)), use_container_width=True)
    st.plotly_chart(build_stack(df, highlight_hour=int(hour)), use_container_width=True)

    with st.expander("Stündliche Tabelle"):
        cols = [
            "Stunde", "Last_GW", "Wind_GW", "PV_GW", "Konv_Soll_GW", "Konv_Min_GW", "Konv_Max_GW",
            "Konv_GW", "Konv_Fehlleistung_GW", "Konv_Mindestlauf_Ueberschuss_GW",
            "Inlaendische_Erzeugung_GW", "Bilanz_vor_BESS_GW", "Zielluecke_vor_BESS_GW",
            "BESS_GW", "BESS_Laden_GW", "BESS_Entladen_GW", "Curtailment_GW",
            "SOC_GWh", "SOC_pct", "Netzbilanz_GW", "Status",
        ]
        st.dataframe(df[[c for c in cols if c in df.columns]].round(3), use_container_width=True)

    with st.expander("SMARD-API Abrufe"):
        if api_meta.empty:
            st.write("Keine API-Metadaten, weil synthetische Quelle aktiv ist.")
        else:
            st.dataframe(api_meta, use_container_width=True)

    with st.expander("PyPSA-Erzeuger / Speicher"):
        st.dataframe(generators.round(4), use_container_width=True)

    with st.expander("PyPSA-Verbraucher-Cluster"):
        st.dataframe(consumers.round(4), use_container_width=True)

    with st.expander("PyPSA-Leitungen und DC-Lastfluss"):
        st.dataframe(line_status.round(4), use_container_width=True)

    with st.expander("DC-Knotensalden und Winkel"):
        nodal_status = line_status.attrs.get("dc_nodal_status", pd.DataFrame())
        if isinstance(nodal_status, pd.DataFrame) and not nodal_status.empty:
            st.dataframe(nodal_status.round(4), use_container_width=True)
        else:
            st.write("Keine Knotensalden verfügbar.")

    with st.expander("Netz-Referenzwerte"):
        st.json(refs)

    st.caption(
        "Topologie und räumliche Verteilung kommen aus real_germany_8n.nc. "
        "Zeitreihen kommen bei SMARD-API-Modus nur für Last/Wind/PV direkt von SMARD. "
        "Restliche Erzeuger sind regelbare Modellleistung. Die App berechnet Leitungsauslastungen mit einer DC-Lastfluss-Näherung, löst aber kein PyPSA-Optimierungsproblem."
    )


if __name__ == "__main__":
    main()
