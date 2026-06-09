from __future__ import annotations

import numpy as np
import pandas as pd

HOURS = np.arange(24)


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

    curtail_frac = float(np.clip(ee_curtail_pct, 0.0, 100.0)) / 100.0
    ee_before = out["Wind_GW"] + out["PV_GW"]
    out["Wind_GW"] *= 1.0 - curtail_frac
    out["PV_GW"] *= 1.0 - curtail_frac
    out["Curtailment_GW"] = ee_before - (out["Wind_GW"] + out["PV_GW"])
    if "Pre_Curtailment_GW" in out.columns:
        out["Curtailment_GW"] += pd.to_numeric(out["Pre_Curtailment_GW"], errors="coerce").fillna(0.0)

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
