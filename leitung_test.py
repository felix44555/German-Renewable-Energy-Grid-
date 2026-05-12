"""
Stromnetzkarte_interaktiv.py
============================
Vereinfachte didaktische Streamlit-App zur Simulation eines 24-Stunden
Stromnetz-Szenarios (Deutschland-aehnlich) mit Last, PV, Wind, Grundlast,
flexiblen Kraftwerken und Batteriespeicher.

Hinweis: Dieses Modell ist eine vereinfachte Lehrsimulation.
Es ersetzt keine Lastflussrechnung, Netzstabilitaetsanalyse oder
Frequenzdynamik-Simulation.

Start: streamlit run Stromnetzkarte_interaktiv.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Globale Modellkonstanten
# ---------------------------------------------------------------------------
HOURS = np.arange(24)
NOMINAL_FREQUENCY = 50.0  # Hz
FREQ_K = 0.03  # Hz / GW  (didaktischer Proxy-Faktor)

# Stabilitaetsbereiche der Frequenz (Hz)
FREQ_STABLE_LOW, FREQ_STABLE_HIGH = 49.8, 50.2
FREQ_WARN_LOW, FREQ_WARN_HIGH = 49.5, 50.5


# ---------------------------------------------------------------------------
# Profilerzeugung
# ---------------------------------------------------------------------------
def generate_profiles(
    load_scale: float = 1.0,
    pv_scale: float = 1.0,
    wind_scale: float = 1.0,
    scenario: str = "standard",
    seed: int = 42,
) -> pd.DataFrame:
    """
    Erzeugt synthetische 24-Stunden-Profile fuer Last, PV, Wind und Grundlast.

    Werte sind in GW. Die Profile orientieren sich grob an der Tagesform
    eines deutschen Stromsystems, sind aber bewusst stilisiert.
    """
    rng = np.random.default_rng(seed)
    h = HOURS

    # --- Last (typischer Tagesverlauf) ---------------------------------
    # Morgenanstieg, Mittagsplateau, Abendpeak
    base_load = (
        55.0
        + 12.0 * np.exp(-((h - 8) ** 2) / 6.0)   # Morgenpeak
        + 8.0 * np.exp(-((h - 13) ** 2) / 10.0)  # Mittagsplateau
        + 18.0 * np.exp(-((h - 19) ** 2) / 5.0)  # Abendpeak
    )

    # --- PV-Erzeugung (Glockenkurve 6..20 Uhr) -------------------------
    pv = np.where(
        (h >= 6) & (h <= 20),
        35.0 * np.exp(-((h - 13) ** 2) / 9.0),
        0.0,
    )

    # --- Wind (geglaettetes Rauschen) ---------------------------------
    raw_wind = rng.normal(loc=20.0, scale=8.0, size=24)
    # gleitender Mittelwert zum Glaetten
    kernel = np.ones(5) / 5.0
    wind = np.convolve(raw_wind, kernel, mode="same")
    wind = np.clip(wind, 2.0, 45.0)

    # --- Grundlast (Kernkraft/Lauf-Wasser/Mueller etc.) ---------------
    baseload = np.full(24, 18.0) + 0.5 * np.sin(h / 24.0 * 2 * np.pi)

    # --- Szenarien-Anpassung ------------------------------------------
    if scenario == "dunkelflaute":
        pv = pv * 0.1
        wind = np.clip(wind * 0.15, 0.5, None)
    elif scenario == "pv_ueberschuss":
        pv = pv * 1.8
        wind = wind * 1.1
    elif scenario == "hohe_abendlast":
        # Abendpeak verstaerken
        evening_boost = 12.0 * np.exp(-((h - 19) ** 2) / 4.0)
        base_load = base_load + evening_boost

    # --- Nutzerseitige Skalierungen -----------------------------------
    load = base_load * load_scale
    pv = pv * pv_scale
    wind = wind * wind_scale

    df = pd.DataFrame(
        {
            "Stunde": h,
            "Last_GW": load,
            "PV_GW": pv,
            "Wind_GW": wind,
            "Grundlast_GW": baseload,
        }
    )
    return df


# ---------------------------------------------------------------------------
# Batterie-Constraint-Check
# ---------------------------------------------------------------------------
def apply_battery_constraints(
    desired_power_gw: float,
    soc_gwh: float,
    capacity_gwh: float,
    p_charge_max: float,
    p_discharge_max: float,
    eta: float,
    soc_min_frac: float,
    soc_max_frac: float,
) -> tuple[float, str | None]:
    """
    Begrenzt einen gewuenschten Batterie-Regelwert auf zulaessige Werte.

    Konvention:
        desired_power_gw > 0  -> Batterie entlaedt (gibt Energie ans Netz)
        desired_power_gw < 0  -> Batterie laedt
        desired_power_gw == 0 -> neutral

    Rueckgabe:
        (zulaessige_leistung, warnung_oder_None)
    """
    warning = None
    soc_min = capacity_gwh * soc_min_frac
    soc_max = capacity_gwh * soc_max_frac

    p = desired_power_gw

    # Leistungsgrenzen
    if p > p_discharge_max:
        warning = f"Entladewunsch {p:.2f} GW > Pmax_dis {p_discharge_max:.2f} GW -> geclampt."
        p = p_discharge_max
    if p < -p_charge_max:
        warning = f"Ladewunsch {p:.2f} GW < -Pmax_ch {p_charge_max:.2f} GW -> geclampt."
        p = -p_charge_max

    # SOC-Grenzen pruefen (1 h Zeitschritt -> Energie = Leistung * 1 h)
    if p > 0:  # entladen
        # entnommene Energie aus Speicher = p / eta_discharge (Verluste beim Entladen)
        energy_taken = p / eta
        if soc_gwh - energy_taken < soc_min:
            allowed_energy = max(soc_gwh - soc_min, 0.0)
            p_new = allowed_energy * eta
            if p_new < p:
                warning = (
                    f"SOC-Untergrenze erreicht: Entladung von {p:.2f} -> {p_new:.2f} GW."
                )
            p = max(p_new, 0.0)
    elif p < 0:  # laden
        charge_power = -p
        energy_stored = charge_power * eta
        if soc_gwh + energy_stored > soc_max:
            allowed_energy = max(soc_max - soc_gwh, 0.0)
            p_charge_new = allowed_energy / eta if eta > 0 else 0.0
            if p_charge_new < charge_power:
                warning = (
                    f"SOC-Obergrenze erreicht: Ladung von {charge_power:.2f} -> {p_charge_new:.2f} GW."
                )
            p = -p_charge_new

    return p, warning


def update_soc(soc_gwh: float, power_gw: float, eta: float) -> float:
    """Aktualisiert den SOC nach 1 h Betrieb mit gegebener Leistung."""
    if power_gw > 0:
        # entladen: aus Speicher fliesst p/eta heraus
        soc_new = soc_gwh - power_gw / eta
    elif power_gw < 0:
        # laden: in Speicher gehen |p|*eta hinein
        soc_new = soc_gwh + (-power_gw) * eta
    else:
        soc_new = soc_gwh
    return max(soc_new, 0.0)


# ---------------------------------------------------------------------------
# Dispatch-Simulation
# ---------------------------------------------------------------------------
def simulate_dispatch(
    profiles: pd.DataFrame,
    params: dict,
    manual_battery: np.ndarray | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Fuehrt den stuendlichen Dispatch durch.

    Reihenfolge (Auto-Modus):
      1) Erneuerbare + Grundlast decken Last.
      2) Ueberschuss laedt Batterie (innerhalb Grenzen).
      3) Defizit -> Batterie entlaedt (innerhalb Grenzen, beachtet Reserve).
      4) Defizit -> flexible Kraftwerke werden hochgefahren.
      5) Restdefizit/Restueberschuss = Netzbilanz (kritisch wenn |.| > Limit).

    Im manuellen Modus wird der User-Wunsch fuer die Batterie geprueft und
    geclampt. Flexible Kraftwerke decken den Rest.
    """
    warnings: list[str] = []

    capacity = params["capacity_gwh"]
    p_ch_max = params["p_charge_max"]
    p_dis_max = params["p_discharge_max"]
    eta = params["eta"]
    soc_min_frac = params["soc_min_frac"]
    soc_max_frac = params["soc_max_frac"]
    soc_start_frac = params["soc_start_frac"]
    reserve_frac = params["reserve_frac"]
    flex_max = params["flex_max"]
    flex_min = params["flex_min"]
    max_underdeckung = params["max_underdeckung"]
    max_ueberdeckung = params["max_ueberdeckung"]

    soc = capacity * soc_start_frac

    rows = []
    for i, row in profiles.iterrows():
        h = int(row["Stunde"])
        load = row["Last_GW"]
        pv = row["PV_GW"]
        wind = row["Wind_GW"]
        baseload_gen = row["Grundlast_GW"]

        # Residuallast = Last - (Erneuerbare + Grundlast)
        residual = load - (pv + wind + baseload_gen)
        # Sicherheitsreserve in GW
        reserve_gw = reserve_frac * load

        # ---- Batterie-Wunsch ermitteln ---------------------------------
        if manual_battery is not None:
            desired = float(manual_battery[i])
        else:
            # Automatischer Dispatch:
            if residual < 0:
                # Ueberschuss -> laden (negativ)
                desired = max(residual, -p_ch_max)
            elif residual > 0:
                # Defizit -> entladen, aber nur soweit, dass flex_max
                # spaeter noch den Rest decken kann
                desired = min(residual, p_dis_max)
            else:
                desired = 0.0

        # ---- Batterie-Constraints anwenden -----------------------------
        batt_power, warn = apply_battery_constraints(
            desired,
            soc,
            capacity,
            p_ch_max,
            p_dis_max,
            eta,
            soc_min_frac,
            soc_max_frac,
        )
        if warn:
            warnings.append(f"Stunde {h:02d}: {warn}")

        # ---- Sicherheitsreserve-Check fuer Entladung -------------------
        if batt_power > 0:
            # SOC nach Entladung
            soc_after = soc - batt_power / eta
            soc_reserve_min = capacity * soc_min_frac + reserve_gw * 0.0
            # einfache Pruefung: SOC darf Reservegrenze nicht unterschreiten
            if soc_after < capacity * soc_min_frac:
                # bereits durch apply_battery_constraints abgefangen
                pass

        # ---- Netz-Residuum nach Batterieaktion -------------------------
        residual_after_batt = residual - batt_power  # positiver Rest = Defizit

        # ---- Flexible Kraftwerke ---------------------------------------
        if residual_after_batt > 0:
            flex = min(max(residual_after_batt, flex_min), flex_max)
        else:
            # auch bei Ueberschuss muss flex_min beruecksichtigt werden,
            # da regelbare Kraftwerke nicht beliebig herunterfahren
            flex = flex_min

        # ---- Netzbilanz: Erzeugung + Entladung - Last - Ladung --------
        gen_total = pv + wind + baseload_gen + flex
        battery_discharge = max(batt_power, 0.0)
        battery_charge = max(-batt_power, 0.0)
        net_balance = gen_total + battery_discharge - battery_charge - load

        # ---- Status ----------------------------------------------------
        status = "stabil"
        reasons = []
        if net_balance < -max_underdeckung:
            status = "kritisch"
            reasons.append("Unterdeckung > Grenze")
        elif net_balance > max_ueberdeckung:
            status = "kritisch"
            reasons.append("Ueberdeckung > Grenze")
        elif abs(net_balance) > 0.5 * min(max_underdeckung, max_ueberdeckung):
            status = "angespannt"

        # SOC-Reserve
        if soc < capacity * soc_min_frac + 1e-9:
            if status != "kritisch":
                status = "angespannt"
            reasons.append("SOC an Untergrenze")

        # Flex-Limit?
        if residual_after_batt > flex_max + 1e-6:
            status = "kritisch"
            reasons.append("Flex-Kraftwerke nicht ausreichend")

        # ---- Frequenzproxy --------------------------------------------
        frequency = NOMINAL_FREQUENCY + FREQ_K * net_balance
        if FREQ_STABLE_LOW <= frequency <= FREQ_STABLE_HIGH:
            freq_status = "stabil"
        elif FREQ_WARN_LOW <= frequency <= FREQ_WARN_HIGH:
            freq_status = "angespannt"
            if status == "stabil":
                status = "angespannt"
        else:
            freq_status = "kritisch"
            status = "kritisch"

        rows.append(
            {
                "Stunde": h,
                "Last_GW": load,
                "PV_GW": pv,
                "Wind_GW": wind,
                "Grundlast_GW": baseload_gen,
                "Flex_GW": flex,
                "Batterie_GW": batt_power,
                "Batt_Laden_GW": battery_charge,
                "Batt_Entladen_GW": battery_discharge,
                "SOC_GWh": soc,
                "SOC_pct": 100.0 * soc / capacity if capacity > 0 else 0.0,
                "Netzbilanz_GW": net_balance,
                "Frequenz_Hz": frequency,
                "Freq_Status": freq_status,
                "Status": status,
                "Gruende": ", ".join(reasons) if reasons else "",
            }
        )

        # ---- SOC-Update fuer naechste Stunde ---------------------------
        soc = update_soc(soc, batt_power, eta)

    df = pd.DataFrame(rows)
    return df, warnings


# ---------------------------------------------------------------------------
# Netz-Status Aggregation
# ---------------------------------------------------------------------------
def calculate_grid_status(df: pd.DataFrame, params: dict) -> dict:
    """Aggregiert die Tageskennzahlen aus dem Simulationsergebnis."""
    capacity = params["capacity_gwh"]
    soc_min = capacity * params["soc_min_frac"]
    soc_max = capacity * params["soc_max_frac"]

    n_crit = int((df["Status"] == "kritisch").sum())
    n_warn = int((df["Status"] == "angespannt").sum())
    n_empty = int((df["SOC_GWh"] <= soc_min + 1e-6).sum())
    n_full = int((df["SOC_GWh"] >= soc_max - 1e-6).sum())

    max_under = float(min(df["Netzbilanz_GW"].min(), 0.0))
    max_over = float(max(df["Netzbilanz_GW"].max(), 0.0))
    f_min = float(df["Frequenz_Hz"].min())
    f_max = float(df["Frequenz_Hz"].max())

    total_load = float(df["Last_GW"].sum())
    renewable = float((df["PV_GW"] + df["Wind_GW"]).sum())
    re_share = 100.0 * renewable / total_load if total_load > 0 else 0.0
    flex_work = float(df["Flex_GW"].sum())  # GWh, da dt = 1 h

    # Ampel
    if n_crit > 0:
        ampel = "ROT"
    elif n_warn > 0:
        ampel = "GELB"
    else:
        ampel = "GRUEN"

    return {
        "ampel": ampel,
        "kritische_stunden": n_crit,
        "angespannte_stunden": n_warn,
        "stunden_batterie_leer": n_empty,
        "stunden_batterie_voll": n_full,
        "max_unterdeckung_GW": max_under,
        "max_ueberdeckung_GW": max_over,
        "min_frequenz_Hz": f_min,
        "max_frequenz_Hz": f_max,
        "re_anteil_pct": re_share,
        "flex_arbeit_GWh": flex_work,
    }


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------
def create_plots(df: pd.DataFrame, params: dict) -> dict:
    """Erzeugt alle Plotly-Diagramme als dict (Name -> Figure)."""
    figs: dict[str, go.Figure] = {}
    h = df["Stunde"]

    # 1) Erzeugung & Last ------------------------------------------------
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=h, y=df["Last_GW"], name="Last", line=dict(color="black", width=3)))
    fig1.add_trace(go.Scatter(x=h, y=df["PV_GW"], name="PV", line=dict(color="orange")))
    fig1.add_trace(go.Scatter(x=h, y=df["Wind_GW"], name="Wind", line=dict(color="steelblue")))
    fig1.add_trace(go.Scatter(x=h, y=df["Grundlast_GW"], name="Grundlast", line=dict(color="gray")))
    fig1.add_trace(go.Scatter(x=h, y=df["Flex_GW"], name="Flexible Erzeugung", line=dict(color="firebrick")))
    fig1.update_layout(
        title="Last und Erzeugung ueber 24 h",
        xaxis_title="Stunde",
        yaxis_title="Leistung [GW]",
        hovermode="x unified",
    )
    figs["erzeugung_last"] = fig1

    # 2) Batterieleistung ------------------------------------------------
    fig2 = go.Figure()
    fig2.add_trace(
        go.Bar(
            x=h,
            y=-df["Batt_Laden_GW"],
            name="Laden (negativ)",
            marker_color="seagreen",
        )
    )
    fig2.add_trace(
        go.Bar(
            x=h,
            y=df["Batt_Entladen_GW"],
            name="Entladen (positiv)",
            marker_color="darkred",
        )
    )
    fig2.update_layout(
        title="Batterieleistung ueber 24 h",
        xaxis_title="Stunde",
        yaxis_title="Leistung [GW]",
        barmode="relative",
        hovermode="x unified",
    )
    figs["batterie_leistung"] = fig2

    # 3) SOC -------------------------------------------------------------
    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(x=h, y=df["SOC_GWh"], name="SOC [GWh]", line=dict(color="purple")))
    fig3.add_trace(
        go.Scatter(
            x=h,
            y=df["SOC_pct"],
            name="SOC [%]",
            line=dict(color="magenta", dash="dot"),
            yaxis="y2",
        )
    )
    fig3.update_layout(
        title="Batterie-Ladezustand (SOC)",
        xaxis_title="Stunde",
        yaxis=dict(title="SOC [GWh]"),
        yaxis2=dict(title="SOC [%]", overlaying="y", side="right", range=[0, 100]),
        hovermode="x unified",
    )
    figs["soc"] = fig3

    # 4) Netzbilanz ------------------------------------------------------
    fig4 = go.Figure()
    fig4.add_trace(
        go.Scatter(x=h, y=df["Netzbilanz_GW"], name="Netzbilanz", line=dict(color="navy"))
    )
    fig4.add_hline(y=0, line_dash="dash", line_color="black")
    fig4.add_hline(
        y=params["max_ueberdeckung"],
        line_dash="dot",
        line_color="red",
        annotation_text="max. Ueberdeckung",
    )
    fig4.add_hline(
        y=-params["max_underdeckung"],
        line_dash="dot",
        line_color="red",
        annotation_text="max. Unterdeckung",
    )
    fig4.update_layout(
        title="Netzbilanz ueber 24 h",
        xaxis_title="Stunde",
        yaxis_title="Bilanz [GW]",
        hovermode="x unified",
    )
    figs["netzbilanz"] = fig4

    # 5) Frequenzproxy ---------------------------------------------------
    fig5 = go.Figure()
    fig5.add_trace(
        go.Scatter(x=h, y=df["Frequenz_Hz"], name="Frequenz-Proxy", line=dict(color="darkgreen"))
    )
    fig5.add_hrect(
        y0=FREQ_STABLE_LOW, y1=FREQ_STABLE_HIGH,
        fillcolor="green", opacity=0.1, line_width=0,
        annotation_text="stabil", annotation_position="top left",
    )
    fig5.add_hrect(
        y0=FREQ_WARN_LOW, y1=FREQ_STABLE_LOW,
        fillcolor="yellow", opacity=0.1, line_width=0,
    )
    fig5.add_hrect(
        y0=FREQ_STABLE_HIGH, y1=FREQ_WARN_HIGH,
        fillcolor="yellow", opacity=0.1, line_width=0,
    )
    fig5.add_hline(y=NOMINAL_FREQUENCY, line_dash="dash", line_color="black")
    fig5.update_layout(
        title="Frequenz-Proxy ueber 24 h (didaktisch)",
        xaxis_title="Stunde",
        yaxis_title="Frequenz [Hz]",
        hovermode="x unified",
    )
    figs["frequenz"] = fig5

    # 6) Versorgungsstapel ----------------------------------------------
    fig6 = go.Figure()
    fig6.add_trace(go.Bar(x=h, y=df["Grundlast_GW"], name="Grundlast", marker_color="gray"))
    fig6.add_trace(go.Bar(x=h, y=df["Wind_GW"], name="Wind", marker_color="steelblue"))
    fig6.add_trace(go.Bar(x=h, y=df["PV_GW"], name="PV", marker_color="orange"))
    fig6.add_trace(go.Bar(x=h, y=df["Batt_Entladen_GW"], name="Batterie Entladung", marker_color="darkred"))
    fig6.add_trace(go.Bar(x=h, y=df["Flex_GW"], name="Flexible Erzeugung", marker_color="firebrick"))
    fig6.add_trace(
        go.Scatter(x=h, y=df["Last_GW"], name="Last", line=dict(color="black", width=3))
    )
    fig6.update_layout(
        barmode="stack",
        title="Versorgungsstapel vs. Last",
        xaxis_title="Stunde",
        yaxis_title="Leistung [GW]",
        hovermode="x unified",
    )
    figs["stack"] = fig6

    return figs


# ---------------------------------------------------------------------------
# Streamlit Main
# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="Stromnetzkarte interaktiv", layout="wide")

    st.title("Stromnetzkarte interaktiv - 24h-Lehrsimulation")
    st.markdown(
        """
        Diese App simuliert vereinfacht einen 24-Stunden-Betriebstag eines
        Deutschland-aehnlichen Stromsystems mit **Last**, **PV**, **Wind**,
        **Grundlast**, **flexiblen Kraftwerken** und **Batteriespeicher**.

        > **Hinweis:** Dieses Modell ist eine vereinfachte Lehrsimulation.
        > Es ersetzt keine Lastflussrechnung, Netzstabilitaetsanalyse oder
        > Frequenzdynamik-Simulation.
        """
    )

    # ---- Szenario-Buttons --------------------------------------------
    if "scenario" not in st.session_state:
        st.session_state.scenario = "standard"

    c1, c2, c3, c4 = st.columns(4)
    if c1.button("Standardszenario laden"):
        st.session_state.scenario = "standard"
    if c2.button("Dunkelflaute-Szenario"):
        st.session_state.scenario = "dunkelflaute"
    if c3.button("PV-Ueberschuss-Szenario"):
        st.session_state.scenario = "pv_ueberschuss"
    if c4.button("Hohe Abendlast"):
        st.session_state.scenario = "hohe_abendlast"

    st.caption(f"Aktives Szenario: **{st.session_state.scenario}**")

    # ---- Sidebar: Parameter ------------------------------------------
    st.sidebar.header("Batterie- und Regelparameter")

    capacity = st.sidebar.slider("Batteriekapazitaet [GWh]", 0.0, 200.0, 50.0, 1.0)
    p_charge_max = st.sidebar.slider("Max. Ladeleistung [GW]", 0.0, 50.0, 10.0, 0.5)
    p_discharge_max = st.sidebar.slider("Max. Entladeleistung [GW]", 0.0, 50.0, 10.0, 0.5)
    eta_pct = st.sidebar.slider("Wirkungsgrad [%]", 50, 100, 90, 1)
    soc_start = st.sidebar.slider("Start-SOC [%]", 0, 100, 50, 1)
    soc_min = st.sidebar.slider("Minimaler SOC [%]", 0, 50, 10, 1)
    soc_max = st.sidebar.slider("Maximaler SOC [%]", 50, 100, 95, 1)
    reserve = st.sidebar.slider("Sicherheitsreserve [% der Last]", 0, 30, 5, 1)

    st.sidebar.header("Flexible Kraftwerke")
    flex_max = st.sidebar.slider("Max. flexible Leistung [GW]", 0.0, 80.0, 40.0, 1.0)
    flex_min = st.sidebar.slider("Min. flexible Leistung [GW]", 0.0, 30.0, 5.0, 0.5)

    st.sidebar.header("Netzgrenzen")
    max_underdeckung = st.sidebar.slider("Max. Unterdeckung [GW]", 0.0, 30.0, 3.0, 0.5)
    max_ueberdeckung = st.sidebar.slider("Max. Ueberdeckung [GW]", 0.0, 30.0, 3.0, 0.5)

    st.sidebar.header("Profilskalierung")
    pv_scale = st.sidebar.slider("PV-Skalierung [%]", 0, 300, 100, 5) / 100.0
    wind_scale = st.sidebar.slider("Wind-Skalierung [%]", 0, 300, 100, 5) / 100.0
    load_scale = st.sidebar.slider("Last-Skalierung [%]", 50, 200, 100, 5) / 100.0

    st.sidebar.header("Modus")
    mode = st.sidebar.radio("Dispatch-Modus", ["Automatisch", "Manuell (Batterie)"])

    params = dict(
        capacity_gwh=capacity,
        p_charge_max=p_charge_max,
        p_discharge_max=p_discharge_max,
        eta=eta_pct / 100.0,
        soc_start_frac=soc_start / 100.0,
        soc_min_frac=soc_min / 100.0,
        soc_max_frac=soc_max / 100.0,
        reserve_frac=reserve / 100.0,
        flex_max=flex_max,
        flex_min=flex_min,
        max_underdeckung=max_underdeckung,
        max_ueberdeckung=max_ueberdeckung,
    )

    # ---- Profile generieren ------------------------------------------
    profiles = generate_profiles(
        load_scale=load_scale,
        pv_scale=pv_scale,
        wind_scale=wind_scale,
        scenario=st.session_state.scenario,
    )

    # ---- Manuelle Batterieeingabe ------------------------------------
    manual_battery = None
    if mode == "Manuell (Batterie)":
        st.subheader("Manuelle Batterie-Regelung")
        st.caption(
            "Werte je Stunde in GW. Negativ = laden, positiv = entladen. "
            "Unzulaessige Eingaben werden automatisch geclampt."
        )
        default_vals = [0.0] * 24
        manual_df = pd.DataFrame(
            {"Stunde": HOURS, "Batterie_GW": default_vals}
        )
        edited = st.data_editor(
            manual_df,
            num_rows="fixed",
            use_container_width=True,
            key="manual_batt_editor",
        )
        manual_battery = edited["Batterie_GW"].to_numpy(dtype=float)

    # ---- Simulation --------------------------------------------------
    df, warnings = simulate_dispatch(profiles, params, manual_battery=manual_battery)
    status = calculate_grid_status(df, params)

    # ---- Ampel & Kennzahlen ------------------------------------------
    st.subheader("Gesamtbewertung")
    ampel_color = {"GRUEN": "green", "GELB": "orange", "ROT": "red"}[status["ampel"]]
    st.markdown(
        f"<div style='padding:1em;border-radius:8px;background:{ampel_color};"
        f"color:white;font-size:1.5em;text-align:center'>"
        f"Netzstatus: {status['ampel']}</div>",
        unsafe_allow_html=True,
    )

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Kritische Stunden", status["kritische_stunden"])
    k2.metric("Angespannte Stunden", status["angespannte_stunden"])
    k3.metric("Batterie leer (h)", status["stunden_batterie_leer"])
    k4.metric("Batterie voll (h)", status["stunden_batterie_voll"])

    k5, k6, k7, k8 = st.columns(4)
    k5.metric("Max. Unterdeckung [GW]", f"{status['max_unterdeckung_GW']:.2f}")
    k6.metric("Max. Ueberdeckung [GW]", f"{status['max_ueberdeckung_GW']:.2f}")
    k7.metric("Min. Frequenz [Hz]", f"{status['min_frequenz_Hz']:.3f}")
    k8.metric("Max. Frequenz [Hz]", f"{status['max_frequenz_Hz']:.3f}")

    k9, k10 = st.columns(2)
    k9.metric("Erneuerbaren-Anteil [%]", f"{status['re_anteil_pct']:.1f}")
    k10.metric("Flex-Arbeit [GWh]", f"{status['flex_arbeit_GWh']:.1f}")

    # ---- Warnungen ---------------------------------------------------
    if warnings:
        with st.expander(f"Warnungen ({len(warnings)})", expanded=False):
            for w in warnings:
                st.warning(w)

    # ---- Plots -------------------------------------------------------
    figs = create_plots(df, params)
    st.subheader("Last & Erzeugung")
    st.plotly_chart(figs["erzeugung_last"], use_container_width=True)

    st.subheader("Versorgungsstapel")
    st.plotly_chart(figs["stack"], use_container_width=True)

    cA, cB = st.columns(2)
    with cA:
        st.subheader("Batterieleistung")
        st.plotly_chart(figs["batterie_leistung"], use_container_width=True)
    with cB:
        st.subheader("SOC-Verlauf")
        st.plotly_chart(figs["soc"], use_container_width=True)

    cC, cD = st.columns(2)
    with cC:
        st.subheader("Netzbilanz")
        st.plotly_chart(figs["netzbilanz"], use_container_width=True)
    with cD:
        st.subheader("Frequenz-Proxy")
        st.plotly_chart(figs["frequenz"], use_container_width=True)

    # ---- Tabelle -----------------------------------------------------
    st.subheader("Stuendliche Werte")
    display_df = df[
        [
            "Stunde", "Last_GW", "PV_GW", "Wind_GW", "Grundlast_GW",
            "Flex_GW", "Batterie_GW", "SOC_GWh", "SOC_pct",
            "Netzbilanz_GW", "Frequenz_Hz", "Status",
        ]
    ].round(3)
    st.dataframe(display_df, use_container_width=True)

    st.caption(
        "Frequenz-Proxy: f = 50 Hz + k * Netzbilanz, k = 0.03 Hz/GW. "
        "Dies ist KEIN reales Frequenzmodell, sondern eine didaktische "
        "Naeherung zur Veranschaulichung von Ungleichgewichten."
    )


if __name__ == "__main__":
    main()