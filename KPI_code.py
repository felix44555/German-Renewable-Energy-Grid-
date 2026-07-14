import pandas as pd

def calculate_feasibility_kpi(re_share_pct, grid_added, bat_added, pv_added, wind_added, max_line_load, derating, tuning_factor=0.05):
    """
    Calculates the engineering feasibility KPI for the grid simulation.
    Derating is now penalized instead of PV and Wind capacity expansion.
    """
    
    # 1. Base Score
    base_score = re_share_pct
    
    # 2. Penalties (Infrastructure & Derating)
    total_penalty_factors = 6.25 * grid_added + bat_added + (20 * derating) 
    
    efficiency_factor = 1.0 / (1.0 + (tuning_factor * total_penalty_factors))
    
    # 3. Stability Constraint
    grid_penalty = 0.00001 if max_line_load > 100.0 else 1.0
    
    # Final KPI
    final_kpi = base_score * efficiency_factor * grid_penalty
    return round(final_kpi, 2)


def _calculate_current_kpi(
    hour_row: pd.Series,
    line_status: pd.DataFrame,
    wind_pct: float,
    pv_pct: float,
    bess_pct: float,
    line_capacity_pct: float,
) -> dict[str, float]:
    """
    Berechnet den Engineering-Feasibility-KPI für die aktuell gewählte Stunde.

    Annahmen:
    - EE-Anteil = (Wind + PV) / Last, auf 0...100 % begrenzt.
    - Ausbauwerte werden als Zusatz gegenüber 100 % Referenz interpretiert.
      Beispiel: 150 % Wind-Slider => wind_added = 0.5.
    - max_line_load kommt aus dem DC-Lastfluss.
    """
    load_gw = max(float(hour_row.get("Last_GW", 0.0)), 1e-9)
    wind_gw = max(float(hour_row.get("Wind_GW", 0.0)), 0.0)
    pv_gw = max(float(hour_row.get("PV_GW", 0.0)), 0.0)
    bess_gw = max(float(hour_row.get("BESS_GW", 0.0)), 0.0)

    re_share_pct = 100.0 * (wind_gw + pv_gw + bess_gw) / load_gw
    re_share_pct = max(0.0, min(re_share_pct, 100.0))
    
    curtailment_gw = max(float(hour_row.get("Curtailment_GW", 0.0)), 0.0)
    curtailment_pct = curtailment_gw / max((wind_gw + pv_gw + bess_gw), 1e-9)
    
    if line_status.empty or "Auslastung_pct" not in line_status.columns:
        max_line_load = 0.0
    else:
        max_line_load = float(
            pd.to_numeric(line_status["Auslastung_pct"], errors="coerce")
            .fillna(0.0)
            .max()
        )

    grid_added = max(float(line_capacity_pct) / 100.0 - 1.0, 0.0)
    bat_added = max(float(bess_pct) / 100.0 - 1.0, 0.0)
    pv_added = max(float(pv_pct) / 100.0 - 1.0, 0.0)
    wind_added = max(float(wind_pct) / 100.0 - 1.0, 0.0)

    kpi = calculate_feasibility_kpi(
        re_share_pct=re_share_pct,
        grid_added=grid_added,
        bat_added=bat_added,
        pv_added=pv_added,
        wind_added=wind_added,
        max_line_load=max_line_load,
        derating=curtailment_pct,
    )

    return {
        "kpi": float(kpi),
        "re_share_pct": float(re_share_pct),
        "max_line_load": float(max_line_load),
        "grid_added": float(grid_added),
        "bat_added": float(bat_added),
        "pv_added": float(pv_added),
        "wind_added": float(wind_added),
    }


def _calculate_24h_kpi(
    df: pd.DataFrame,
    generators: pd.DataFrame,
    consumers: pd.DataFrame,
    lines: pd.DataFrame,
    wind_pct: float,
    pv_pct: float,
    bess_pct: float,
    line_capacity_pct: float,
    line_stress_factor: float,
    line_status: dict[int, pd.DataFrame],
    
) -> dict[str, float | pd.DataFrame]:
    """
    Berechnet eine Tages-KPI-Zahl über alle 24 Stunden.

    Definition:
    - re_share_pct_24h = Summe(Wind + PV) / Summe(Last) über 24h
    - max_line_load_24h = höchste Leitungsauslastung aus allen 24 DC-Lastflussrechnungen
    - Ausbauwerte = Zusatz gegenüber 100 % Sliderwert
    """

    total_load_gwh = float(pd.to_numeric(df["Last_GW"], errors="coerce").fillna(0.0).sum())
    #Greift auf Spalte "LastGW" zu ersetzt alle ungültigen Datentypen durch NAN, ersetzt alle NAN durch 0.0'''
    total_re_gwh = float(
        (
            pd.to_numeric(df["Wind_GW"], errors="coerce").fillna(0.0)
            + pd.to_numeric(df["PV_GW"], errors="coerce").fillna(0.0)
            +pd.to_numeric(df["BESS_GW"], errors="coerce").fillna(0.0)
        ).sum()
    )

    re_share_pct_24h = 100.0 * total_re_gwh / max(total_load_gwh, 1e-9)
    #max() um Division durch 0 zu vermeiden'''
    re_share_pct_24h = max(0.0, min(re_share_pct_24h, 100.0))
    #sorgt dafür das Wert zwischen 0 und 100 ist'''
    
    total_curtailment_gwh = float(
        (
            pd.to_numeric(df["Curtailment_GW"], errors="coerce").fillna(0.0)
        ).sum()
    )
    curtailment_pct_24h = total_curtailment_gwh / max(total_load_gwh, 1e-9)
    
    hourly_rows: list[dict[str, float]] = []
    max_line_load_24h = 0.0
    overloaded_hours = 0

    for stunde_idx, row in df.iterrows():
        line_status_h = line_status[stunde_idx]
        if line_status_h.empty or "Auslastung_pct" not in line_status_h.columns:
            max_line_h = 0.0
            overloaded_count_h = 0
        else:
            util = pd.to_numeric(line_status_h["Auslastung_pct"], errors="coerce").fillna(0.0)
            max_line_h = float(util.max())
            overloaded_count_h = int((util > 100.0).sum())

        if max_line_h > 100.0:
            overloaded_hours += 1

        max_line_load_24h = max(max_line_load_24h, max_line_h)

        hourly_rows.append(
            {
                "Stunde": int(row.get("Stunde", 0)),
                "Last_GW": float(row.get("Last_GW", 0.0)),
                "Wind_GW": float(row.get("Wind_GW", 0.0)),
                "PV_GW": float(row.get("PV_GW", 0.0)),
                "Netzbilanz_GW": float(row.get("Netzbilanz_GW", 0.0)),
                "Max_Leitung_pct": max_line_h,
                "Ueberlastete_Leitungen": overloaded_count_h,
            }
        )

    grid_added = max(float(line_capacity_pct) / 100.0 - 1.0, 0.0)
    bat_added = max(float(bess_pct) / 100.0 - 1.0, 0.0)
    pv_added = max(float(pv_pct) / 100.0 - 1.0, 0.0)
    wind_added = max(float(wind_pct) / 100.0 - 1.0, 0.0)

    kpi_24h = calculate_feasibility_kpi(
        re_share_pct=re_share_pct_24h,
        grid_added=grid_added,
        bat_added=bat_added,
        pv_added=pv_added,
        wind_added=wind_added,
        max_line_load=max_line_load_24h,
        derating = curtailment_pct_24h,
    )

    return {
        "kpi_24h": float(kpi_24h),
        "re_share_pct_24h": float(re_share_pct_24h),
        "max_line_load_24h": float(max_line_load_24h),
        "overloaded_hours": int(overloaded_hours),
        "total_load_gwh": float(total_load_gwh),
        "total_re_gwh": float(total_re_gwh),
        "grid_added": float(grid_added),
        "bat_added": float(bat_added),
        "pv_added": float(pv_added),
        "wind_added": float(wind_added),
        "hourly_kpi_table": pd.DataFrame(hourly_rows),
    }