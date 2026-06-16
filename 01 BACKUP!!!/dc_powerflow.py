from __future__ import annotations

import numpy as np
import pandas as pd


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(out):
        return default
    return out


def _line_reactance_ohm(row: pd.Series) -> float:
    """Liefert positive Serienreaktanz in Ohm; bei fehlendem x wird transparent geschätzt."""
    x = _as_float(row.get("X_Ohm", row.get("x", np.nan)), np.nan)
    if np.isfinite(x) and abs(x) > 1e-9:
        return abs(x)

    length_km = _as_float(row.get("Laenge_km", row.get("length", 0.0)), 0.0)
    num_parallel = max(_as_float(row.get("Num_parallel", row.get("num_parallel", 1.0)), 1.0), 1e-6)
    v_nom = _as_float(row.get("V_nom_kV", row.get("v_nom", 380.0)), 380.0)

    typical_x_ohm_per_km = 0.30 if v_nom >= 300.0 else 0.40
    if length_km > 0.0:
        return typical_x_ohm_per_km * length_km / num_parallel

    cap_gw = _as_float(row.get("Kapazitaet_GW", 0.0), 0.0)
    if cap_gw > 0.0 and v_nom > 0.0:
        max_angle_rad = np.deg2rad(20.0)
        return (v_nom**2) / max(cap_gw * 1000.0 / max_angle_rad, 1e-9)

    return 1.0


def _branch_susceptance_gw_per_rad(row: pd.Series) -> float:
    """DC-Suszeptanz b in GW/rad aus U^2/X."""
    x_ohm = max(_line_reactance_ohm(row), 1e-9)
    v_nom = max(_as_float(row.get("V_nom_kV", 380.0), 380.0), 1.0)
    return (v_nom**2) / x_ohm / 1000.0


def _compute_nodal_injections_gw(
    generators: pd.DataFrame,
    consumers: pd.DataFrame,
    buses: list[str],
    hour_row: pd.Series,
) -> pd.DataFrame:
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
        nodal["Wind_GW"] + nodal["PV_GW"] + nodal["Konv_GW"] + nodal["BESS_GW"] - nodal["Last_GW"]
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
    if not component:
        return 0
    scores: list[tuple[float, int]] = []
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
    Löst B_bus * theta = P je Netzinsel.

    Die P-Werte werden als Python-Liste geführt, damit keine read-only NumPy-Views
    in-place beschrieben werden. Das verhindert den bisherigen Streamlit/Pandas-Fehler.
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
        imbalance = float(sum(float(p[idx]) for idx in comp))
        p[slack] = float(p[slack]) - imbalance
        nodal.loc[bus_names[slack], "Slack_Ausgleich_GW"] -= imbalance
        nodal.loc[bus_names[slack], "P_nach_Slack_GW"] = float(p[slack])

        active = [idx for idx in comp if idx != slack]
        bred = bbus[np.ix_(active, active)]
        pred = np.asarray([p[idx] for idx in active], dtype=float)
        try:
            theta_active = np.linalg.solve(bred, pred)
        except np.linalg.LinAlgError:
            theta_active = np.linalg.pinv(bred) @ pred
        theta[active] = theta_active
        theta[slack] = 0.0

    nodal["Theta_rad"] = theta
    nodal["Theta_grad"] = np.rad2deg(theta)
    return theta, nodal


def compute_dc_line_status(
    generators: pd.DataFrame,
    consumers: pd.DataFrame,
    lines: pd.DataFrame,
    hour_row: pd.Series,
    line_capacity_pct: float,
    line_stress_factor: float = 1.0,
) -> pd.DataFrame:
    """Berechnet Leitungsauslastung mit einer DC-Lastfluss-Näherung."""
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

    for (_, ln), b in zip(out.iterrows(), b_values):
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
    out["Flow_Proxy_GW"] = abs_flows  # Kompatibilitätsalias für bestehende Diagramme.
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


# Kompatibilitätsname, falls vorhandene UI/Tests noch den alten Funktionsnamen erwarten.
compute_line_status_proxy = compute_dc_line_status
