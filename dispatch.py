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


def _as_nonnegative_float(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(out):
        return default
    return max(out, 0.0)


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
    Dispatch-Modell mit geänderter Merit-Order der Netzstützung:

    1. Wind/PV/Last werden skaliert.
    2. Konventioneller Mindestbetrieb gilt als must-run, nicht als flexible Netzstützung.
    3. BESS stützt zuerst: Entladung bei Unterdeckung, Ladung bei Überschuss.
    4. Erst danach fahren restliche/konventionelle Erzeuger oberhalb des Mindestbetriebs hoch.
    5. EE-Abregelung wird erst am Ende angewendet und nur dann, wenn tatsächlich Überschuss bleibt.

    Vorzeichen BESS_GW:
    - positiv  = Entladung / Einspeisung
    - negativ  = Ladung / zusätzliche Last
    """
    out = profiles.copy()
    for col in ("Wind_GW", "PV_GW", "Last_GW"):
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0).clip(lower=0.0)

    out["Wind_GW"] *= _as_nonnegative_float(wind_scale, 1.0)
    out["PV_GW"] *= _as_nonnegative_float(pv_scale, 1.0)
    out["Last_GW"] *= _as_nonnegative_float(load_scale, 1.0)

    # Werte vor der dynamischen EE-Abregelung sichern.
    out["Wind_vor_Abregelung_GW"] = out["Wind_GW"]
    out["PV_vor_Abregelung_GW"] = out["PV_GW"]
    out["EE_vor_Abregelung_GW"] = out["Wind_GW"] + out["PV_GW"]

    if "Pre_Curtailment_GW" in out.columns:
        pre_curtail = pd.to_numeric(out["Pre_Curtailment_GW"], errors="coerce").fillna(0.0).reset_index(drop=True)
    else:
        pre_curtail = pd.Series(0.0, index=range(len(out)), dtype=float)

    konv_max = max(float(refs.get("konv_gw", 0.0)) * _as_nonnegative_float(konv_scale, 1.0), 0.0)
    konv_min = konv_max * float(np.clip(konv_min_pct, 0.0, 100.0)) / 100.0
    konv_flex_max = max(konv_max - konv_min, 0.0)

    p_bess_max = max(float(refs.get("bess_gw", 0.0)) * _as_nonnegative_float(bess_scale, 1.0), 0.0)
    cap_bess = max(float(refs.get("bess_gwh", 0.0)) * _as_nonnegative_float(bess_scale, 1.0), 0.0)
    eta = float(np.clip(eta, 1e-6, 1.0))

    soc = cap_bess * float(np.clip(soc_start_pct, 0.0, 100.0)) / 100.0
    soc_min = 0.10 * cap_bess
    soc_max = 0.95 * cap_bess

    curtail_frac = float(np.clip(ee_curtail_pct, 0.0, 100.0)) / 100.0

    wind_final: list[float] = []
    pv_final: list[float] = []
    konv_p: list[float] = []
    konv_soll: list[float] = []
    konv_fehl: list[float] = []
    konv_min_surplus: list[float] = []
    bess_p: list[float] = []
    bess_charge: list[float] = []
    bess_discharge: list[float] = []
    soc_track: list[float] = []
    curtailment: list[float] = []
    balance_before_bess: list[float] = []
    residual_before_bess: list[float] = []
    residual_after_bess_values: list[float] = []
    balance_before_curtail: list[float] = []
    status: list[str] = []

    for pos, (_, row) in enumerate(out.iterrows()):
        load = float(row["Last_GW"])
        wind = float(row["Wind_GW"])
        pv = float(row["PV_GW"])
        ee = wind + pv

        # Konv_min ist Mindestbetrieb. Flexible konventionelle Leistung wird erst nach BESS genutzt.
        residual_before = load - ee - konv_min
        residual_before_bess.append(residual_before)
        balance_before_bess.append(-residual_before)

        b_power = 0.0
        if cap_bess > 0.0 and p_bess_max > 0.0:
            if residual_before > 1e-9:
                # Unterdeckung: BESS entlädt zuerst.
                discharge_power = min(residual_before, p_bess_max)
                energy_taken = discharge_power / eta
                if soc - energy_taken < soc_min:
                    energy_taken = max(soc - soc_min, 0.0)
                    discharge_power = energy_taken * eta
                soc -= energy_taken
                b_power = discharge_power
            elif residual_before < -1e-9:
                # Überschuss: BESS lädt zuerst.
                charge_power = min(-residual_before, p_bess_max)
                energy_stored = charge_power * eta
                if soc + energy_stored > soc_max:
                    energy_stored = max(soc_max - soc, 0.0)
                    charge_power = energy_stored / eta if eta > 0 else 0.0
                soc += energy_stored
                b_power = -charge_power

        residual_after_bess = residual_before - b_power
        residual_after_bess_values.append(residual_after_bess)

        # Flexible restliche Erzeuger erst nach BESS.
        flex_target = max(residual_after_bess, 0.0)
        flex_konv = min(flex_target, konv_flex_max)
        k_power = konv_min + flex_konv
        k_soll = konv_min + flex_target
        k_fehl = max(k_soll - konv_max, 0.0)

        balance_pre_curt = ee + k_power + b_power - load

        # EE-Abregelung: keine pauschale Vorab-Kürzung, sondern nur realer Überschuss wird reduziert.
        # Der Slider ist damit eine Obergrenze: 0 % = keine Abregelung, 80 % = maximal 80 % der aktuellen EE.
        curtail_allowed = curtail_frac * ee
        curtail = 0.0
        if balance_pre_curt > 1e-9 and curtail_allowed > 0.0 and ee > 0.0:
            curtail = min(balance_pre_curt, curtail_allowed, ee)
            wind_share = wind / ee if ee > 0.0 else 0.0
            pv_share = pv / ee if ee > 0.0 else 0.0
            wind -= curtail * wind_share
            pv -= curtail * pv_share

        final_balance = wind + pv + k_power + b_power - load
        total_curtail = float(pre_curtail.iloc[pos]) + curtail

        if final_balance < -1.0:
            stat = "Unterdeckung"
        elif final_balance > 1.0:
            stat = "Ueberschuss"
        elif total_curtail > 0.5:
            stat = "Abregelung"
        else:
            stat = "stabil"

        wind_final.append(wind)
        pv_final.append(pv)
        konv_p.append(k_power)
        konv_soll.append(k_soll)
        konv_fehl.append(k_fehl)
        konv_min_surplus.append(max(-residual_after_bess, 0.0))
        bess_p.append(b_power)
        bess_charge.append(max(-b_power, 0.0))
        bess_discharge.append(max(b_power, 0.0))
        soc_track.append(soc)
        curtailment.append(total_curtail)
        balance_before_curtail.append(balance_pre_curt)
        status.append(stat)

    out["Wind_GW"] = wind_final
    out["PV_GW"] = pv_final
    out["Konv_Min_GW"] = konv_min
    out["Konv_Max_GW"] = konv_max
    out["Konv_Flex_Max_GW"] = konv_flex_max
    out["Konv_Soll_GW"] = konv_soll
    out["Konv_GW"] = konv_p
    out["Konv_Fehlleistung_GW"] = konv_fehl
    out["Konv_Mindestlauf_Ueberschuss_GW"] = konv_min_surplus
    out["BESS_GW"] = bess_p
    out["BESS_Laden_GW"] = bess_charge
    out["BESS_Entladen_GW"] = bess_discharge
    out["SOC_GWh"] = soc_track
    out["SOC_pct"] = [s / cap_bess * 100.0 if cap_bess > 0.0 else 0.0 for s in soc_track]
    out["Curtailment_GW"] = curtailment
    out["Bilanz_vor_BESS_GW"] = balance_before_bess
    out["Zielluecke_vor_BESS_GW"] = residual_before_bess
    out["Zielluecke_nach_BESS_vor_Konv_GW"] = residual_after_bess_values
    out["Bilanz_vor_Abregelung_GW"] = balance_before_curtail
    out["Inlaendische_Erzeugung_GW"] = out["Wind_GW"] + out["PV_GW"] + out["Konv_GW"]
    out["Netzbilanz_GW"] = out["Inlaendische_Erzeugung_GW"] + out["BESS_GW"] - out["Last_GW"]
    out["Status"] = status
    return out
