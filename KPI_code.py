def calculate_feasibility_kpi(re_share_pct, grid_added, bat_added, pv_added, wind_added, max_line_load, tuning_factor=0.1):
    """
    Calculates the engineering feasibility KPI for the grid simulation.
    """
    # 1. Base Score
    base_score = re_share_pct
    
    # 2. Infrastructure Bloat
    total_new_infrastructure = grid_added + bat_added + pv_added + wind_added
    efficiency_factor = 1.0 / (1.0 + (tuning_factor * total_new_infrastructure))
    
    # 3. Stability Constraint
    grid_penalty = 0.05 if max_line_load > 100.0 else 1.0
    
    # Final KPI
    final_kpi = base_score * efficiency_factor * grid_penalty
    return round(final_kpi, 2)