from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd


def _read_smard_csv(path: str | Path) -> pd.DataFrame:
    """Read a SMARD CSV with German decimal format and semicolon separator."""
    df = pd.read_csv(
        path,
        sep=";",
        decimal=",",
        thousands=".",
        na_values=["-", "", " "],
        encoding="utf-8-sig",
    )
    df["timestamp"] = pd.to_datetime(df["Datum von"], format="%d.%m.%Y %H:%M")
    return df


def _sum_existing(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    existing = [c for c in cols if c in df.columns]
    if not existing:
        return pd.Series(0.0, index=df.index)
    return df[existing].apply(pd.to_numeric, errors="coerce").fillna(0.0).sum(axis=1)


def load_smard_dispatch_profile(
    generation_csv: str | Path,
    load_csv: str | Path,
    installed_capacity_csv: str | Path | None = None,
    date: str | None = None,
    pct_basis: str = "total_installed",
    load_pct_reference: str = "mean",
) -> pd.DataFrame:
    """
    Convert SMARD quarter-hour CSV files into the simplified 24 h dispatch profile.

    Output columns fit the existing scenario_tools code:
        Stunde, Wind_GW, PV_GW, Konv_GW, Last_GW, Netzbilanz_GW, Curtailment_GW,
        Wind_pct, PV_pct, Konv_pct, Load_pct

    Interpretation:
    - pct_basis="total_installed": all percentages are normalised to the same denominator:
      total installed generation capacity = Wind + PV + Konv capacity. This includes Load_pct.
    - pct_basis="own_capacity": Wind/PV/Konv are normalised to their own installed capacity.
      Load_pct is then normalised to the chosen daily load reference.
    - Konv_GW contains all non-wind/PV generation available in the SMARD generation file.
      This keeps the simplified model balanced better because biomass, hydro etc. are not
      separate technologies in the GUI.
    """
    gen = _read_smard_csv(generation_csv)
    load = _read_smard_csv(load_csv)

    if date is not None:
        day = pd.to_datetime(date).date()
        gen = gen[gen["timestamp"].dt.date == day].copy()
        load = load[load["timestamp"].dt.date == day].copy()

    gen_cols_wind = [
        "Wind Offshore [MWh] Originalauflösungen",
        "Wind Onshore [MWh] Originalauflösungen",
    ]
    gen_cols_pv = ["Photovoltaik [MWh] Originalauflösungen"]
    gen_cols_all_non_wind_pv = [
        "Biomasse [MWh] Originalauflösungen",
        "Wasserkraft [MWh] Originalauflösungen",
        "Sonstige Erneuerbare [MWh] Originalauflösungen",
        "Kernenergie [MWh] Originalauflösungen",
        "Braunkohle [MWh] Originalauflösungen",
        "Steinkohle [MWh] Originalauflösungen",
        "Erdgas [MWh] Originalauflösungen",
        "Pumpspeicher [MWh] Originalauflösungen",
        "Sonstige Konventionelle [MWh] Originalauflösungen",
    ]

    # Quarter-hour values are energy in MWh. Summing four quarters gives hourly MWh,
    # numerically equal to average MW over that hour.
    g = pd.DataFrame(
        {
            "timestamp": gen["timestamp"],
            "Wind_MWh": _sum_existing(gen, gen_cols_wind),
            "PV_MWh": _sum_existing(gen, gen_cols_pv),
            "Konv_MWh": _sum_existing(gen, gen_cols_all_non_wind_pv),
        }
    )
    l = pd.DataFrame(
        {
            "timestamp": load["timestamp"],
            "Last_MWh": pd.to_numeric(
                load["Netzlast [MWh] Originalauflösungen"], errors="coerce"
            ).fillna(0.0),
        }
    )

    hourly_gen = g.set_index("timestamp").resample("1h").sum()
    hourly_load = l.set_index("timestamp").resample("1h").sum()
    hourly = hourly_gen.join(hourly_load, how="inner")

    out = pd.DataFrame(index=hourly.index)
    out["Stunde"] = out.index.hour
    out["Wind_GW"] = hourly["Wind_MWh"] / 1000.0
    out["PV_GW"] = hourly["PV_MWh"] / 1000.0
    out["Konv_GW"] = hourly["Konv_MWh"] / 1000.0
    out["Last_GW"] = hourly["Last_MWh"] / 1000.0
    out["BESS_GW"] = 0.0
    out["Curtailment_GW"] = 0.0
    out["Netzbilanz_GW"] = out["Wind_GW"] + out["PV_GW"] + out["Konv_GW"] + out["BESS_GW"] - out["Last_GW"]

    if installed_capacity_csv is not None:
        cap = _read_smard_csv(installed_capacity_csv)
        if date is not None:
            cap = cap[cap["timestamp"].dt.date == pd.to_datetime(date).date()].copy()

        wind_cap_mw = _sum_existing(
            cap,
            [
                "Wind Offshore [MW] Berechnete Auflösungen",
                "Wind Onshore [MW] Berechnete Auflösungen",
            ],
        ).replace(0.0, np.nan)
        pv_cap_mw = _sum_existing(cap, ["Photovoltaik [MW] Berechnete Auflösungen"]).replace(0.0, np.nan)
        konv_cap_mw = _sum_existing(
            cap,
            [
                "Biomasse [MW] Berechnete Auflösungen",
                "Wasserkraft [MW] Berechnete Auflösungen",
                "Sonstige Erneuerbare [MW] Berechnete Auflösungen",
                "Kernenergie [MW] Berechnete Auflösungen",
                "Braunkohle [MW] Berechnete Auflösungen",
                "Steinkohle [MW] Berechnete Auflösungen",
                "Erdgas [MW] Berechnete Auflösungen",
                "Pumpspeicher [MW] Berechnete Auflösungen",
                "Sonstige Konventionelle [MW] Berechnete Auflösungen",
            ],
        ).replace(0.0, np.nan)

        c = pd.DataFrame(
            {
                "timestamp": cap["timestamp"],
                "Wind_cap_MW": wind_cap_mw,
                "PV_cap_MW": pv_cap_mw,
                "Konv_cap_MW": konv_cap_mw,
            }
        ).set_index("timestamp").resample("1h").mean()

        out = out.join(c, how="left")
        out["Total_installed_cap_MW"] = (
            out["Wind_cap_MW"] + out["PV_cap_MW"] + out["Konv_cap_MW"]
        )

        if pct_basis == "total_installed":
            denom = out["Total_installed_cap_MW"].replace(0.0, np.nan)
            out["Wind_pct"] = 100.0 * out["Wind_GW"] * 1000.0 / denom
            out["PV_pct"] = 100.0 * out["PV_GW"] * 1000.0 / denom
            out["Konv_pct"] = 100.0 * out["Konv_GW"] * 1000.0 / denom
            out["Load_pct"] = 100.0 * out["Last_GW"] * 1000.0 / denom
        elif pct_basis == "own_capacity":
            out["Wind_pct"] = 100.0 * out["Wind_GW"] * 1000.0 / out["Wind_cap_MW"]
            out["PV_pct"] = 100.0 * out["PV_GW"] * 1000.0 / out["PV_cap_MW"]
            out["Konv_pct"] = 100.0 * out["Konv_GW"] * 1000.0 / out["Konv_cap_MW"]

            if load_pct_reference == "max":
                ref = out["Last_GW"].max()
            elif load_pct_reference == "mean":
                ref = out["Last_GW"].mean()
            else:
                raise ValueError("load_pct_reference must be 'mean' or 'max'")
            out["Load_pct"] = 100.0 * out["Last_GW"] / max(float(ref), 1e-9)
        else:
            raise ValueError("pct_basis must be 'total_installed' or 'own_capacity'")
    else:
        out["Wind_pct"] = np.nan
        out["PV_pct"] = np.nan
        out["Konv_pct"] = np.nan
        out["Load_pct"] = np.nan

    return out.reset_index(names="timestamp")


def smard_defaults_for_hour(profile: pd.DataFrame, hour: int) -> dict[str, int]:
    """Return slider defaults from one hour of a SMARD-derived profile."""
    row = profile.loc[profile["Stunde"].astype(int) == int(hour)].iloc[0]
    return {
        "wind_pct": int(round(row["Wind_pct"])),
        "pv_pct": int(round(row["PV_pct"])),
        "load_pct": int(round(row["Load_pct"])),
        "hour": int(hour),
        # If you use the existing app sliders, this can be used as conventional generation slider.
        "konv_pct": int(round(row["Konv_pct"])),
    }
