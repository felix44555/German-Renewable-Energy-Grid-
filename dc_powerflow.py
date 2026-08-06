from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

def _as_float(value: object, default: float = 0.0) -> float:
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

    Priorität:
    1. X_Ohm oder x aus dem Netzmodell
    2. Schätzung über Leitungslänge
    3. Schätzung über Kapazität
    4. Fallback 1 Ohm

    Wichtig:
    Das ist kein Slack-Fallback. Es betrifft nur fehlende Leitungsdaten.
    """
    x = _as_float(row.get("X_Ohm", row.get("x", np.nan)), np.nan)

    if np.isfinite(x) and abs(x) > 1e-9:
        return abs(x)

    length_km = _as_float(row.get("Laenge_km", row.get("length", 0.0)), 0.0)
    num_parallel = max(
        _as_float(row.get("Num_parallel", row.get("num_parallel", 1.0)), 1.0),
        1e-6,
    )
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
    """
    Berechnet die DC-Suszeptanz b in GW/rad.

    Formel:
        b = U^2 / X

    Einheit:
        U in kV
        X in Ohm
        Ergebnis in GW/rad
    """
    x_ohm = max(_line_reactance_ohm(row), 1e-9)
    v_nom = max(_as_float(row.get("V_nom_kV", 380.0), 380.0), 1.0)

    return (v_nom**2) / x_ohm / 1000.0


def _compute_nodal_injections_gw( #Ermittelt Last am Knoten
    generators: pd.DataFrame,
    consumers: pd.DataFrame,
    buses: list[str],
    hour_row: pd.Series,
) -> pd.DataFrame:
    """
    Berechnet feste Knotensalden für den DC-Loadflow.

    Vorzeichenkonvention:
    - Erzeugung positiv
    - BESS positiv = Entladung / Einspeisung
    - BESS negativ = Ladung / zusätzliche Last
    - Last negativ

    Wichtig:
    - keine Slack-Korrektur
    - keine künstliche Last
    - keine künstliche Erzeugung
    """
    nodal = pd.DataFrame(index=pd.Index(buses, name="Bus"))

    for col in ("Wind_GW", "PV_GW", "Konv_GW", "BESS_GW", "Last_GW"):
        nodal[col] = 0.0

    typ_to_col = {
        "Wind": "Wind_GW",
        "PV": "PV_GW",
        "Konventionell": "Konv_GW",
        "BESS": "BESS_GW",
    }

    typ_power = {
        typ: _as_float(hour_row.get(col, 0.0), 0.0)
        for typ, col in typ_to_col.items()
    }

    if not generators.empty and "Bus" in generators.columns:
        for _, gen in generators.iterrows():
            bus = str(gen.get("Bus", ""))
            typ = str(gen.get("Typ", ""))

            if bus not in nodal.index:
                continue

            if typ not in typ_to_col:
                continue

            share = _as_float(gen.get("Anteil", 0.0), 0.0)
            nodal.loc[bus, typ_to_col[typ]] += share * typ_power[typ]
            
 # -----------------------------------------------------------------
    # NEU: MANUELLE KNOTEN-ANPASSUNGEN FÜR WIND (Sauber!)
    # -----------------------------------------------------------------
    if not generators.empty and "Bus" in generators.columns:
        
        if st.session_state.get("scenario_key") == "Wind2":
            nodal["Wind_GW"] = 0.0 # Wir bauen Wind manuell neu auf
            effective_wind_ratio = st.session_state.get("effective_wind_ratio")
            # WICHTIG: Da hour_row["Wind_GW"] schon reduziert ist, müssen wir
            # kurz zurückrechnen, was 100% Wind gewesen wären, um es korrekt zu verteilen
            # (Verhindert Division-by-Zero, falls gar kein Wind weht)
            if effective_wind_ratio > 0.01:
                base_wind_global = typ_power["Wind"] / effective_wind_ratio
            else:
                base_wind_global = 0.0
            
            for gen_idx, gen in generators.iterrows():
                typ = str(gen.get("Typ", ""))
                bus = str(gen.get("Bus", ""))

                if typ == "Wind":
                    share = _as_float(gen.get("Anteil", 0.0), 0.0)
                    
                    try:
                        knoten_nummer = int(bus.replace("DE0 ", "").strip())
                        state_key = f"wind_node_{knoten_nummer}"
                        slider_prozent = st.session_state.get(state_key, 100) / 100.0
                    except ValueError:
                        slider_prozent = 1.0
                        
                    # Lokalen Wind berechnen und exakt auf diesen Knoten schreiben
                    lokaler_wind = share * base_wind_global * slider_prozent
                    
                    if bus in nodal.index:
                        nodal.loc[bus, "Wind_GW"] += lokaler_wind
                        
    # -----------------------------------------------------------------
    # ENDE NEU
    # -----------------------------------------------------------------
    
    total_load = _as_float(hour_row.get("Last_GW", 0.0), 0.0)

    if not consumers.empty and "Bus" in consumers.columns:
        for _, load in consumers.iterrows():
            bus = str(load.get("Bus", ""))

            if bus not in nodal.index:
                continue

            share = _as_float(load.get("Anteil", 0.0), 0.0)
            nodal.loc[bus, "Last_GW"] += share * total_load

    nodal["P_Knotensaldo_GW"] = (
        nodal["Wind_GW"]
        + nodal["PV_GW"]
        + nodal["Konv_GW"]
        + nodal["BESS_GW"]
        - nodal["Last_GW"]
    )


    # Kompatibilität / eindeutige Anzeige
    nodal["P_Loadflow_GW"] = nodal["P_Knotensaldo_GW"]
    nodal["Theta_rad"] = 0.0
    nodal["Theta_grad"] = 0.0
    nodal["Ist_Referenzbus"] = False
    nodal["Netzinsel"] = -1
    nodal["Netzinsel_Bilanz_GW"] = 0.0

    return nodal


def _connected_components(
    n_buses: int,
    branches: list[tuple[int, int, float]],
) -> list[list[int]]:
    """
    Ermittelt zusammenhängende Netzinseln.

    Bei einem vollständig zusammenhängenden Netz gibt es genau eine Komponente.
    Bei mehreren Komponenten muss jede Komponente für sich bilanziert sein.
    """
    adjacency: list[list[int]] = [[] for _ in range(n_buses)]

    for i, j, b in branches:
        if b <= 0.0 or not np.isfinite(b):
            continue

        adjacency[i].append(j)
        adjacency[j].append(i)

    seen = [False] * n_buses
    components: list[list[int]] = []

    for start in range(n_buses):
        if seen[start]:
            continue

        stack = [start]
        seen[start] = True
        component: list[int] = []

        while stack:
            node = stack.pop()
            component.append(node)

            for neighbor in adjacency[node]:
                if not seen[neighbor]:
                    seen[neighbor] = True
                    stack.append(neighbor)

        components.append(sorted(component))

    return components


def _choose_reference_bus(
    component: list[int],
    bus_names: list[str],
    nodal: pd.DataFrame,
) -> int:
    """
    Wählt einen mathematischen Referenzbus innerhalb einer Netzinsel.
    -> den mit der gröten Leistungsdifferenz (bezog oder einspeisung)
    Wichtig:
    - Das ist kein Slackbus.
    - Der Bus setzt nur theta = 0.
    - Es wird keine Leistung auf diesen Bus gelegt.(außer die sowieso vorhandene)
    """
    if not component:
        return 0
    '''
    scores: list[tuple[float, int]] = []

    for idx in component:
        bus = bus_names[idx]
        row = nodal.loc[bus]

        score = (
            abs(_as_float(row.get("Last_GW", 0.0), 0.0))
            + abs(_as_float(row.get("Konv_GW", 0.0), 0.0))
            + abs(_as_float(row.get("Wind_GW", 0.0), 0.0))
            + abs(_as_float(row.get("PV_GW", 0.0), 0.0))
            + abs(_as_float(row.get("BESS_GW", 0.0), 0.0))
        )

        scores.append((score, idx))

    return max(scores)[1]
    '''
    return component[0];

def _solve_dc_angles(
    bus_names: list[str],
    branches: list[tuple[int, int, float]],
    nodal: pd.DataFrame,
    balance_tol_gw: float = 1e-6,
) -> tuple[np.ndarray, pd.DataFrame]:
    """
    DC-Lastfluss ohne Slack-Ausgleich.

    Modell:
        B' * theta = P
        P_ij = b_ij * (theta_i - theta_j)

    Eigenschaften:
    - P ist vollständig vorgegeben.
    - Summe(P) muss je Netzinsel 0 sein.
    - Referenzbus setzt nur theta = 0.
    - keine künstliche Last
    - keine künstliche Erzeugung
    - kein Fallback auf Slackbus
    """

    n_buses = len(bus_names)

    if n_buses == 0:
        return np.array([], dtype=float), nodal

    # ------------------------------------------------------------
    # 1. B'-Matrix aufbauen
    # ------------------------------------------------------------
    B_prime = np.zeros((n_buses, n_buses), dtype=float)

    for i, j, b in branches:
        b = float(b)

        if b <= 0.0 or not np.isfinite(b):
            continue

        B_prime[i, i] += b
        B_prime[j, j] += b
        B_prime[i, j] -= b
        B_prime[j, i] -= b

    # ------------------------------------------------------------
    # 2. Feste Knotensalden lesen
    # ------------------------------------------------------------
    p = (
        pd.to_numeric(nodal["P_Loadflow_GW"], errors="coerce")
        .fillna(0.0)
        .astype(float)
        .to_numpy()
    )

    theta = np.zeros(n_buses, dtype=float)

    components = _connected_components(n_buses=n_buses, branches=branches)

    nodal["Ist_Referenzbus"] = False
    nodal["Netzinsel"] = -1
    nodal["Netzinsel_Bilanz_GW"] = 0.0

    # ------------------------------------------------------------
    # 3. Jede Netzinsel separat prüfen und lösen
    # ------------------------------------------------------------
    for component_id, component in enumerate(components, start=1):
        component_balance = float(np.sum(p[component]))

        for idx in component:
            nodal.loc[bus_names[idx], "Netzinsel"] = component_id
            nodal.loc[bus_names[idx], "Netzinsel_Bilanz_GW"] = component_balance

        if abs(component_balance) > balance_tol_gw:
            component_buses = ", ".join(bus_names[idx] for idx in component)

            if component_balance > 0.0:
                state = "Überdeckung"
            else:
                state = "Unterdeckung"

            raise ValueError(
                f"DC-Lastfluss abgebrochen: Netzinsel {component_id} ist nicht ausbalanciert "
                f"({state}, Summe(P) = {component_balance:+.9f} GW). "
                f"Busse: {component_buses}. "
                "Es wird keine Restleistung auf einen Referenzknoten gelegt."
            )

        ref_bus = _choose_reference_bus(
            component=component,
            bus_names=bus_names,
            nodal=nodal,
        )

        nodal.loc[bus_names[ref_bus], "Ist_Referenzbus"] = True

        active_buses = [idx for idx in component if idx != ref_bus]

        # Einzelner isolierter Bus: nur erlaubt, wenn P = 0.
        if not active_buses:
            theta[ref_bus] = 0.0
            continue

        B_red = B_prime[np.ix_(active_buses, active_buses)]
        P_red = p[active_buses]

        try:
            theta_red = np.linalg.solve(B_red, P_red)
        except np.linalg.LinAlgError as exc:
            component_buses = ", ".join(bus_names[idx] for idx in component)

            raise ValueError(
                f"DC-Lastfluss abgebrochen: B'-Matrix der Netzinsel {component_id} ist singulär. "
                f"Busse: {component_buses}. "
                "Prüfe Leitungen, Reaktanzen und ob die Netzinsel korrekt verbunden ist."
            ) from exc

        for pos, bus_idx in enumerate(active_buses):
            theta[bus_idx] = float(theta_red[pos])

        theta[ref_bus] = 0.0

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
    """
    Berechnet Leitungsauslastungen mit DC-Lastfluss ohne Slack-Ausgleich.

    Erwartung:
    - Das Dispatch-Modell muss vorher Erzeugung, BESS, Abregelung und Last so setzen,
      dass jede Netzinsel bilanziert ist.
    - Diese Funktion erzeugt keine künstliche Last und keine künstliche Erzeugung.
    """

    if lines.empty:
        return lines.copy()

    out = lines.copy()

    buses = sorted( #hier wird ein sortiertes Set erstelkl aus den unterschiedlichen Quellen für Nodes (jeder kommt nur einmal vor da Set)

        set(out["von"].astype(str))
        .union(set(out["nach"].astype(str)))
        .union(set(generators.get("Bus", pd.Series(dtype=str)).astype(str)))
        .union(set(consumers.get("Bus", pd.Series(dtype=str)).astype(str)))
    )

    bus_to_idx = {bus: idx for idx, bus in enumerate(buses)}

    nodal = _compute_nodal_injections_gw(
        generators=generators,
        consumers=consumers,
        buses=buses,
        hour_row=hour_row,
    )

    branches: list[tuple[int, int, float]] = [] #Deklarierung: Jedes Tuple besteht aus zwei Integern (die Start-/Ziel-Indizes) und einem Float (der Suszeptanz $B$).
    b_values: list[float] = [] 
    x_values: list[float] = []

    for _, ln in out.iterrows():
        bus0 = str(ln.get("von", ""))
        bus1 = str(ln.get("nach", ""))

        if bus0 not in bus_to_idx or bus1 not in bus_to_idx:
            continue

        b = _branch_susceptance_gw_per_rad(ln)
        x = _line_reactance_ohm(ln)

        b_values.append(b)
        x_values.append(x)
        branches.append((bus_to_idx[bus0], bus_to_idx[bus1], b))

    theta, nodal = _solve_dc_angles(
        bus_names=buses,
        branches=branches,
        nodal=nodal,
    )

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

    # Kompatibilitätsalias für bestehende Diagramme
    out["Flow_Proxy_GW"] = abs_flows

    out["Auslastung_pct"] = util_values
    out["Ueberlast"] = overload_flags

    out["Netzbilanz_Loadflow_GW"] = float(nodal["P_Loadflow_GW"].sum())
    out["Referenzbus"] = ", ".join(
        nodal.index[nodal["Ist_Referenzbus"] == True].astype(str).tolist()
    )
    out["Szenario_Flow_Faktor"] = stress

    nodal_out = nodal.reset_index()

    out.attrs["dc_nodal_status"] = nodal_out
    out.attrs["dc_loadflow_valid"] = True
    out.attrs["dc_loadflow_message"] = (
        "DC-Lastfluss gültig: Knotensalden sind bilanziert. "
        "Kein Slack-Ausgleich, Referenzbus nur für theta = 0."
    )
    out.attrs["dc_model_note"] = (
        "DC-Lastfluss: P_ij = b_ij * (theta_i - theta_j), "
        "verlustlos, konstante Spannung, kein Slack-Ausgleich. "
        "Der Referenzbus setzt nur theta = 0."
    )

    return out


# Kompatibilitätsname, falls vorhandene UI/Tests noch den alten Namen erwarten.
compute_line_status_proxy = compute_dc_line_status


def find_max_line_utilization_24h(line_status_24h: dict[int, pd.DataFrame]) -> int:
    max_hour = 0
    max_util = -1.0
    
    for hour, df in line_status_24h.items():
        # Sicherheitscheck, ob Daten vorhanden sind
        if not df.empty and "Auslastung_pct" in df.columns:
            # .max() sucht extrem schnell den höchsten Wert in der ganzen Spalte
            current_max = float(df["Auslastung_pct"].max()) 
            
            if current_max > max_util:
                max_util = current_max
                max_hour = hour
                
    return max_hour