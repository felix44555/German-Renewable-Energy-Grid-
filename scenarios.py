from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from texts import TXT_SCEN

lang = st.session_state.get("lang", "DE")

default_day = date.today() - timedelta(days=2)

SCENARIOS: dict[str, dict[str, Any]] = {
    "training": {
        "name": TXT_SCEN[lang]["Scen_Train_Name"],
        "task": TXT_SCEN[lang]["Scen_Train_Task"],
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
            "smard_day": default_day,
            "date_locked": False,
        },
        "profile_factors": {"wind": 1.00, "pv": 1.00, "load": 1.00},
        "line_stress_factor": 1.00,
        "limits": {"balance_abs_gw": 1.0, "max_curtailment_gw": 6.0, "max_line_util_pct": 100.0},
    },
    "Wind": {
        "name": TXT_SCEN[lang]["Scen_Wind_Name"],
        "task": TXT_SCEN[lang]["Scen_Wind_Task"],
        "defaults": {
            "wind_pct": 100,
            "pv_pct": 100,
            "konv_pct": 100,
            "konv_min_pct": 0,
            "bess_pct": 100,
            "load_pct": 140,
            "soc_pct": 50,
            "line_capacity_pct": 100,
            "ee_curtail_pct": 0,
            "hour": 19,
            "smard_day": date(2026, 2, 2),
            "date_locked": True,
        },
        "profile_factors": {"wind": 2.00, "pv": 1.00, "load": 1.00},
        "line_stress_factor": 1.00,
        "limits": {"balance_abs_gw": 1.0, "max_curtailment_gw": 6.0, "max_line_util_pct": 100.0},
    },
    "Sonne": {
        "name": TXT_SCEN[lang]["Scen_Sun_Name"],
        "task": TXT_SCEN[lang]["Scen_Sun_Task"],
        "defaults": {
            "wind_pct": 100,
            "pv_pct": 100,
            "konv_pct": 100,
            "konv_min_pct": 0,
            "bess_pct": 100,
            "load_pct": 120,
            "soc_pct": 50,
            "line_capacity_pct": 100,
            "ee_curtail_pct": 0,
            "hour": 9,
            "smard_day": date(2025, 6, 20),
            "date_locked": True,
        },
        "profile_factors": {"wind": 1.0, "pv": 2.0, "load": 1.0},
        "line_stress_factor": 1,
        "limits": {"balance_abs_gw": 1.0, "max_curtailment_gw": 6.0, "max_line_util_pct": 100.0},
    },
    "WindSonne": {
        "name": TXT_SCEN[lang]["Scen_WindSun_Name"],
        "task": TXT_SCEN[lang]["Scen_WindSun_Task"],
        "defaults": {
            "wind_pct": 100,
            "pv_pct": 100,
            "konv_pct": 100,
            "konv_min_pct": 0,
            "bess_pct": 100,
            "load_pct": 120,
            "soc_pct": 50,
            "line_capacity_pct": 100,
            "ee_curtail_pct": 0,
            "hour": 7,
            "smard_day": date(2025, 4, 15),
            "date_locked": True,
        },
        "profile_factors": {"wind": 1.5, "pv": 1.5, "load": 1.0},
        "line_stress_factor": 1,
        "limits": {"balance_abs_gw": 1.0, "max_curtailment_gw": 6.0, "max_line_util_pct": 100.0},
    },
    "Wind2": {
        "name": TXT_SCEN[lang]["Scen_Wind2_Name"],
        "task": TXT_SCEN[lang]["Scen_Wind2_Task"],
        "defaults": {
            "wind_pct": 100,
            "pv_pct": 100,
            "konv_pct": 100,
            "konv_min_pct": 0,
            "bess_pct": 100,
            "load_pct": 140,
            "soc_pct": 50,
            "line_capacity_pct": 100,
            "ee_curtail_pct": 0,
            "hour": 19,
            "smard_day": date(2026, 2, 2),
            "date_locked": True,
        },
        "profile_factors": {"wind": 2.00, "pv": 1.00, "load": 1.00},
        "line_stress_factor": 1.00,
        "limits": {"balance_abs_gw": 1.0, "max_curtailment_gw": 6.0, "max_line_util_pct": 100.0},
    },
}


def apply_scenario_to_profiles(
    profiles: pd.DataFrame,
    scenario_key: str,
    ee_curtail_pct: float = 0.0,
) -> pd.DataFrame:
    """Wendet Szenariofaktoren auf SMARD-orientierte Größen an: Last, Wind, PV."""
    scenario = SCENARIOS.get(scenario_key, SCENARIOS["training"])
    factors = scenario.get("profile_factors", {})
    out = profiles.copy()

    for col, key in (("Wind_GW", "wind"), ("PV_GW", "pv"), ("Last_GW", "load")):
        if col in out.columns: # testet ob col Wert vorkommt
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0) * float(factors.get(key, 1.0)) #aufschlagung der Faktoren

    out["Pre_Curtailment_GW"] = 0.0
    if ee_curtail_pct: #gesammte if Bedingung nicht ausgeführt da Abregelung von EE 0
        curtail_frac = max(0.0, min(float(ee_curtail_pct), 100.0)) / 100.0
        old_ee = out.get("Wind_GW", 0.0) + out.get("PV_GW", 0.0)
        if "Wind_GW" in out.columns:
            out["Wind_GW"] *= 1.0 - curtail_frac
        if "PV_GW" in out.columns:
            out["PV_GW"] *= 1.0 - curtail_frac
        new_ee = out.get("Wind_GW", 0.0) + out.get("PV_GW", 0.0)
        out["Pre_Curtailment_GW"] = old_ee - new_ee

    return out


def evaluate_scenario(hour_row: pd.Series, line_status: pd.DataFrame, scenario_key: str) -> dict[str, Any]:
    """Bewertet, ob Bilanz, Abregelung und Leitungsauslastung innerhalb der Szenariogrenzen liegen."""
    
    # Sprach-Abruf hier erneut ausführen, damit dynamische Auswertungen immer die aktuell gewählte Sprache nutzen
    lang = st.session_state.get("lang", "DE")
    
    scenario = SCENARIOS.get(scenario_key, SCENARIOS["training"])
    limits = scenario.get("limits", {})
    balance_limit = float(limits.get("balance_abs_gw", 1.0))
    curtail_limit = float(limits.get("max_curtailment_gw", 6.0))
    line_limit = float(limits.get("max_line_util_pct", 100.0))

    balance = float(hour_row.get("Netzbilanz_GW", 0.0))
    #curtailment = float(hour_row.get("Curtailment_GW", 0.0))
    curtailment = 0.0

    if line_status.empty or "Auslastung_pct" not in line_status.columns:
        peak_line = 0.0
        overloaded_count = 0
    else:
        util = pd.to_numeric(line_status["Auslastung_pct"], errors="coerce").fillna(0.0)
        peak_line = float(util.max())
        overloaded_count = int((util > line_limit).sum())

    messages: list[str] = []
    if abs(balance) <= balance_limit:
        messages.append(TXT_SCEN[lang]["Eval_Bal_OK"].format(balance, balance_limit))
    elif balance < -balance_limit:
        messages.append(TXT_SCEN[lang]["Eval_Bal_Under"].format(balance))
    else:
        messages.append(TXT_SCEN[lang]["Eval_Bal_Over"].format(balance))

    if curtailment <= curtail_limit:
        messages.append(TXT_SCEN[lang]["Eval_Curtail_OK"].format(curtailment, curtail_limit))
    else:
        messages.append(TXT_SCEN[lang]["Eval_Curtail_High"].format(curtailment, curtail_limit))

    if overloaded_count == 0:
        messages.append(TXT_SCEN[lang]["Eval_Lines_OK"].format(peak_line))
    else:
        messages.append(TXT_SCEN[lang]["Eval_Lines_Over"].format(overloaded_count, peak_line))

    solved = abs(balance) <= balance_limit and curtailment <= curtail_limit and overloaded_count == 0
    return {
        "solved": solved,
        "messages": messages,
        "balance_gw": balance,
        "curtailment_gw": curtailment,
        "peak_line_util_pct": peak_line,
        "overloaded_count": overloaded_count,
    }