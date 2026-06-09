"""
Deutschlandkarte_Netz.py
========================
Vereinfachte interaktive Deutschland-Karte (Entwurf v2):
  - 4 Verbraucher-Cluster
  - 10 Uebertragungsleitungen
  - Erzeuger: Wind, PV, BESS, Konventionell
  - 24h-Zeitslider mit Tagesprofilen
  - Skalierungs-Slider 0..300 % fuer Wind, PV und Batterie
    (Basis = 100 % entspricht aktuellen, vereinfachten Referenzwerten DE)
  - Balkendiagramm Last vs. Erzeugung pro Stunde (Stack)

Hinweis: ENTWURF / didaktische Lehrsimulation.
Kein reales Netzmodell, keine Lastflussrechnung.

Referenzwerte (100 %) sind grob orientiert an der aktuellen installierten
Leistung in Deutschland (Stand 2024/2025, gerundet, vereinfacht):
  Wind  ~ 70 GW (Onshore + Offshore zusammen, hier vereinfacht)
  PV    ~ 90 GW
  BESS  ~ 12 GW Leistung / 17 GWh Kapazitaet (grosse Speicher, grob)
  Konv. ~ 80 GW (Gas, Kohle, Biomasse, Wasser zusammen)

Start:
    pip install streamlit pandas numpy plotly
    streamlit run Deutschlandkarte_Netz.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# ---------------------------------------------------------------------------
# Referenzwerte (entsprechen 100 % der Slider)
# ---------------------------------------------------------------------------
REF_WIND_GW = 70.0   # installierte Leistung Wind gesamt
REF_PV_GW = 90.0     # installierte Leistung PV gesamt
REF_KONV_GW = 80.0   # regelbare konventionelle/Bio/Wasser
REF_BESS_GW = 12.0   # BESS Leistung
REF_BESS_GWH = 17.0  # BESS Energie

HOURS = np.arange(24)


# ---------------------------------------------------------------------------
# Stammdaten
# ---------------------------------------------------------------------------
def get_generators() -> pd.DataFrame:
    """
    Erzeuger-Standorte mit Anteil an der jeweiligen Bundes-Gesamtleistung.
    'Anteil' summiert sich pro Typ zu 1.0.
    """
    data = [
        # Wind
        ("Wind Offshore Nord",  "Wind", 54.5,  7.5, 0.18),
        ("Wind Norddeutschland","Wind", 53.5,  9.5, 0.45),
        ("Wind Ost",            "Wind", 52.3, 13.0, 0.25),
        ("Wind Mitte/West",     "Wind", 51.6,  8.0, 0.12),
        # PV
        ("PV Sueden",           "PV",   48.6, 11.0, 0.45),
        ("PV Mitte/West",       "PV",   50.5,  8.5, 0.30),
        ("PV Ost",              "PV",   51.8, 12.5, 0.15),
        ("PV Nord",             "PV",   53.2,  9.5, 0.10),
        # Konventionell
        ("Konv. West (Ruhr)",   "Konventionell", 51.5,  7.0, 0.40),
        ("Konv. Sued",          "Konventionell", 48.6, 11.5, 0.25),
        ("Konv. Ost",           "Konventionell", 52.2, 13.0, 0.20),
        ("Konv. Nord",          "Konventionell", 53.4,  9.8, 0.15),
        # BESS
        ("BESS Nord",           "BESS", 53.4,  9.9, 0.25),
        ("BESS West",           "BESS", 51.3,  7.0, 0.30),
        ("BESS Mitte",          "BESS", 50.3, 10.0, 0.20),
        ("BESS Sued",           "BESS", 48.6, 11.5, 0.25),
    ]
    return pd.DataFrame(
        data, columns=["Name", "Typ", "lat", "lon", "Anteil"]
    )


def get_consumer_clusters() -> pd.DataFrame:
    """
    4 Verbraucher-Cluster (Ballungsraeume).
    Lastanteile sind grob, summieren sich auf 1.0.
    Spitzenlast Deutschland ~ 75 GW; hier verwenden wir Tagesmittel ~ 60 GW
    als 100 %-Bezug fuer die Last (per Skalierung anpassbar).
    """
    data = [
        ("Nord (Hamburg/Hannover)",  53.0,  9.7, 0.20),
        ("West (NRW/Rhein-Main)",    51.0,  7.5, 0.40),
        ("Sued (BW/Bayern)",         48.5, 11.0, 0.30),
        ("Ost (Berlin/Sachsen)",     52.0, 13.0, 0.10),
    ]
    return pd.DataFrame(
        data, columns=["Cluster", "lat", "lon", "Anteil"]
    )


def get_lines(consumers: pd.DataFrame) -> pd.DataFrame:
    """
    10 vereinfachte Uebertragungsleitungen.
    Mischung aus:
      - Erzeugungsregionen -> Cluster
      - Cluster -> Cluster Verbindungen (Backbone)
    """
    c = {row["Cluster"]: (row["lat"], row["lon"]) for _, row in consumers.iterrows()}

    # Erzeugungs-Knotenpunkte (vereinfachte Sammelpunkte je Typ/Region)
    nodes = {
        "Wind Nord":   (54.0,  9.0),
        "Wind Ost":    (52.3, 13.0),
        "PV Sued":     (48.6, 11.0),
        "PV Mitte":    (50.5,  8.5),
        "Konv. West":  (51.5,  7.0),
        "Konv. Sued":  (48.6, 11.5),
    }

    lines = [
        # 1-2: HGUe-aehnlich Nord -> Sued/West
        ("L1 Nord->Sued",  "Wind Nord",  "Sued (BW/Bayern)",        4.0),
        ("L2 Nord->West",  "Wind Nord",  "West (NRW/Rhein-Main)",   4.0),
        # 3-4: PV Sued -> West/Ost
        ("L3 PVSued->West","PV Sued",    "West (NRW/Rhein-Main)",   3.0),
        ("L4 PVSued->Ost", "PV Sued",    "Ost (Berlin/Sachsen)",    2.5),
        # 5: PV Mitte -> West
        ("L5 PVMitte->West","PV Mitte",  "West (NRW/Rhein-Main)",   3.0),
        # 6: Wind Ost -> Ost-Cluster
        ("L6 WindOst->Ost","Wind Ost",   "Ost (Berlin/Sachsen)",    3.5),
        # 7: Konv. West -> West-Cluster
        ("L7 Konv->West",  "Konv. West", "West (NRW/Rhein-Main)",   4.5),
        # 8: Konv. Sued -> Sued-Cluster
        ("L8 Konv->Sued",  "Konv. Sued", "Sued (BW/Bayern)",        4.0),
        # 9-10: Cluster-Backbone
        ("L9 Nord<->West", "Nord (Hamburg/Hannover)", "West (NRW/Rhein-Main)", 3.0),
        ("L10 West<->Sued","West (NRW/Rhein-Main)",  "Sued (BW/Bayern)",       3.5),
    ]

    rows = []
    for name, a, b, cap in lines:
        lat0, lon0 = nodes[a] if a in nodes else c[a]
        lat1, lon1 = nodes[b] if b in nodes else c[b]
        rows.append(
            dict(
                Name=name, von=a, nach=b,
                lat0=lat0, lon0=lon0, lat1=lat1, lon1=lon1,
                Kapazitaet_GW=cap,
            )
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Profile (24 h)
# ---------------------------------------------------------------------------
def generate_profiles(
    wind_scale: float,
    pv_scale: float,
    bess_scale: float,
    load_scale: float = 1.0,
    seed: int = 7,
) -> pd.DataFrame:
    """
    Erzeugt Tagesprofile der Erzeugungsleistung [GW] fuer 24 h.
    Slider 100 % -> Referenzwerte (REF_*).
    """
    rng = np.random.default_rng(seed)
    h = HOURS

    # --- Last (Tagesmittel ~ 60 GW als 100 %-Basis) -------------------
    base_load_profile = (
        55.0
        + 12.0 * np.exp(-((h - 8) ** 2) / 6.0)
        + 8.0  * np.exp(-((h - 13) ** 2) / 10.0)
        + 18.0 * np.exp(-((h - 19) ** 2) / 5.0)
    ) * load_scale

    # --- PV ----------------------------------------------------------
    pv_shape = np.where(
        (h >= 6) & (h <= 20),
        np.exp(-((h - 13) ** 2) / 9.0),
        0.0,
    )
    pv_peak_factor = 0.55  # Mittagsspitze ~ 55 % der Inst.leistung
    pv_total = REF_PV_GW * pv_scale * pv_peak_factor * pv_shape

    # --- Wind --------------------------------------------------------
    raw_wind = rng.normal(loc=0.45, scale=0.18, size=24)
    kernel = np.ones(5) / 5.0
    wind_factor = np.convolve(raw_wind, kernel, mode="same")
    wind_factor = np.clip(wind_factor, 0.08, 0.85)
    wind_total = REF_WIND_GW * wind_scale * wind_factor

    # --- Konv. (regelbar, hier Mittelwert um 25 GW) ------------------
    konv_total = np.full(24, 20.0)  # Initialwert, wird in Dispatch ueberschrieben

    df = pd.DataFrame({
        "Stunde": h,
        "Last_GW":  base_load_profile,
        "PV_GW":    pv_total,
        "Wind_GW":  wind_total,
        "Konv_GW":  konv_total,
    })
    return df


def simulate_dispatch(
    df: pd.DataFrame,
    bess_scale: float,
    soc_start_pct: float = 50.0,
    eta: float = 0.9,
) -> pd.DataFrame:
    """
    Sehr einfache Merit-Order Simulation:
      - Erneuerbare decken Last zuerst.
      - Ueberschuss -> BESS laden (bis P_max / Kapazitaet erreicht).
      - Defizit -> BESS entladen (bis P_max / SOC_min erreicht).
      - Restdefizit -> Konv. zuschalten (bis REF_KONV_GW).
      - Restdefizit danach -> Unterdeckung (kritisch).
    """
    p_bess_max = REF_BESS_GW * bess_scale
    cap_bess   = REF_BESS_GWH * bess_scale
    soc = cap_bess * soc_start_pct / 100.0
    soc_min = 0.10 * cap_bess
    soc_max = 0.95 * cap_bess

    konv = []
    bess_p = []
    soc_track = []
    bilanz = []
    status = []

    for _, row in df.iterrows():
        load = row["Last_GW"]
        pv = row["PV_GW"]
        wind = row["Wind_GW"]
        residual = load - (pv + wind)

        # ---- BESS ----
        if residual < 0:
            # Ueberschuss -> laden
            charge_power = min(-residual, p_bess_max)
            energy_stored = charge_power * eta
            if soc + energy_stored > soc_max:
                energy_stored = max(soc_max - soc, 0.0)
                charge_power = energy_stored / eta if eta > 0 else 0.0
            soc += energy_stored
            b_power = -charge_power  # negativ = laden
        elif residual > 0:
            # Defizit -> entladen
            discharge_power = min(residual, p_bess_max)
            energy_taken = discharge_power / eta
            if soc - energy_taken < soc_min:
                energy_taken = max(soc - soc_min, 0.0)
                discharge_power = energy_taken * eta
            soc -= energy_taken
            b_power = discharge_power  # positiv = entladen
        else:
            b_power = 0.0

        # ---- Konv. ----
        residual2 = residual - b_power
        if residual2 > 0:
            k = min(residual2, REF_KONV_GW)
        else:
            k = 0.0

        # ---- Netzbilanz ----
        gen = pv + wind + k + max(b_power, 0.0)
        ch = max(-b_power, 0.0)
        nb = gen - ch - load

        # ---- Status ----
        if nb < -1.0:
            stat = "kritisch"
        elif nb > 1.0:
            stat = "Ueberschuss"
        else:
            stat = "stabil"

        konv.append(k)
        bess_p.append(b_power)
        soc_track.append(soc)
        bilanz.append(nb)
        status.append(stat)

    out = df.copy()
    out["Konv_GW"] = konv
    out["BESS_GW"] = bess_p
    out["BESS_Laden_GW"]    = [max(-x, 0.0) for x in bess_p]
    out["BESS_Entladen_GW"] = [max(x, 0.0) for x in bess_p]
    out["SOC_GWh"] = soc_track
    out["SOC_pct"] = [s / cap_bess * 100.0 if cap_bess > 0 else 0.0 for s in soc_track]
    out["Netzbilanz_GW"] = bilanz
    out["Status"] = status
    return out


# ---------------------------------------------------------------------------
# Farben / Symbole
# ---------------------------------------------------------------------------
TYP_COLORS = {
    "Wind":          "#1f77b4",
    "PV":            "#ff7f0e",
    "BESS":          "#2ca02c",
    "Konventionell": "#7f7f7f",
    "Verbraucher":   "#d62728",
    "Leitung":       "#444444",
}

TYP_SYMBOLS = {
    "Wind":          "triangle-up",
    "PV":            "square",
    "BESS":          "diamond",
    "Konventionell": "circle",
    "Verbraucher":   "star",
}


# ---------------------------------------------------------------------------
# Karte
# ---------------------------------------------------------------------------
def build_map(
    generators: pd.DataFrame,
    consumers: pd.DataFrame,
    lines: pd.DataFrame,
    hour_row: pd.Series,
    wind_scale: float,
    pv_scale: float,
    bess_scale: float,
) -> go.Figure:
    """Karte mit aktuellen stuendlichen Werten."""
    fig = go.Figure()

    # ---- Leitungen ---------------------------------------------------
    # Auslastung grob: Anteil der Summe |Erzeugung - Last| pro Linie als Indikator
    total_gen = hour_row["PV_GW"] + hour_row["Wind_GW"] + hour_row["Konv_GW"] + hour_row["BESS_Entladen_GW"]
    load = hour_row["Last_GW"]
    factor = min(1.5, max(0.2, total_gen / max(load, 1e-3)))

    for _, ln in lines.iterrows():
        # Auslastung pro Linie ~ Kapazitaet * factor (vereinfachter Proxy)
        util = min(1.0, factor * 0.6)
        color = "green" if util < 0.6 else ("orange" if util < 0.9 else "red")
        fig.add_trace(
            go.Scattergeo(
                lon=[ln["lon0"], ln["lon1"]],
                lat=[ln["lat0"], ln["lat1"]],
                mode="lines",
                line=dict(width=2 + 4 * util, color=color),
                opacity=0.7,
                hoverinfo="text",
                text=f"{ln['Name']} ({ln['von']} -> {ln['nach']})<br>"
                     f"Kapazitaet: {ln['Kapazitaet_GW']:.1f} GW<br>"
                     f"Proxy-Auslastung: {util*100:.0f} %",
                showlegend=False,
            )
        )

    # ---- Erzeuger ---------------------------------------------------
    typ_to_value = {
        "Wind":          hour_row["Wind_GW"],
        "PV":            hour_row["PV_GW"],
        "BESS":          hour_row["BESS_GW"],
        "Konventionell": hour_row["Konv_GW"],
    }
    typ_to_inst = {
        "Wind":          REF_WIND_GW * wind_scale,
        "PV":            REF_PV_GW   * pv_scale,
        "BESS":          REF_BESS_GW * bess_scale,
        "Konventionell": REF_KONV_GW,
    }

    for typ in ["Wind", "PV", "BESS", "Konventionell"]:
        sub = generators[generators["Typ"] == typ]
        if sub.empty:
            continue
        akt_total = typ_to_value[typ]
        inst_total = typ_to_inst[typ]
        # Werte pro Standort = Anteil * akt_total
        sub = sub.assign(
            Aktuell_GW=sub["Anteil"] * akt_total,
            Installiert_GW=sub["Anteil"] * inst_total,
        )
        fig.add_trace(
            go.Scattergeo(
                lon=sub["lon"],
                lat=sub["lat"],
                text=[
                    f"<b>{n}</b><br>Typ: {typ}<br>"
                    f"Aktuell: {a:.2f} GW<br>Installiert: {i:.2f} GW"
                    for n, a, i in zip(sub["Name"], sub["Aktuell_GW"], sub["Installiert_GW"])
                ],
                hoverinfo="text",
                mode="markers",
                name=typ,
                marker=dict(
                    size=10 + np.abs(sub["Aktuell_GW"]) * 2.0,
                    color=TYP_COLORS[typ],
                    symbol=TYP_SYMBOLS[typ],
                    line=dict(width=1, color="black"),
                    opacity=0.9,
                ),
            )
        )

    # ---- Verbraucher-Cluster ----------------------------------------
    cluster_load = consumers["Anteil"] * hour_row["Last_GW"]
    fig.add_trace(
        go.Scattergeo(
            lon=consumers["lon"],
            lat=consumers["lat"],
            text=[
                f"<b>{c}</b><br>Last aktuell: {l:.2f} GW"
                for c, l in zip(consumers["Cluster"], cluster_load)
            ],
            hoverinfo="text",
            mode="markers+text",
            name="Verbraucher-Cluster",
            textposition="top center",
            textfont=dict(size=11, color="black"),
            marker=dict(
                size=14 + cluster_load * 1.2,
                color=TYP_COLORS["Verbraucher"],
                symbol=TYP_SYMBOLS["Verbraucher"],
                line=dict(width=1.2, color="black"),
                opacity=0.9,
            ),
        )
    )

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
        lataxis_range=[47.0, 55.5],
        lonaxis_range=[5.0, 16.0],
    )

    fig.update_layout(
        height=620,
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=-0.05, x=0.5, xanchor="center"),
    )
    return fig


# ---------------------------------------------------------------------------
# Balkendiagramm Last vs. Erzeugung (Stack)
# ---------------------------------------------------------------------------
def build_stack(df: pd.DataFrame, highlight_hour: int) -> go.Figure:
    h = df["Stunde"]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=h, y=df["Wind_GW"], name="Wind", marker_color=TYP_COLORS["Wind"]))
    fig.add_trace(go.Bar(x=h, y=df["PV_GW"],   name="PV",   marker_color=TYP_COLORS["PV"]))
    fig.add_trace(go.Bar(x=h, y=df["BESS_Entladen_GW"], name="BESS Entladen", marker_color=TYP_COLORS["BESS"]))
    fig.add_trace(go.Bar(x=h, y=df["Konv_GW"], name="Konventionell", marker_color=TYP_COLORS["Konventionell"]))
    fig.add_trace(go.Bar(
        x=h, y=-df["BESS_Laden_GW"], name="BESS Laden",
        marker_color="rgba(44,160,44,0.5)",
    ))
    fig.add_trace(go.Scatter(
        x=h, y=df["Last_GW"], name="Last",
        line=dict(color="black", width=3),
    ))
    # Hoehenmarkierung der aktuellen Stunde
    fig.add_vline(x=highlight_hour, line_dash="dash", line_color="red")
    fig.update_layout(
        barmode="relative",
        title="Last vs. Erzeugung (Stack) - aktuelle Stunde rot markiert",
        xaxis_title="Stunde",
        yaxis_title="Leistung [GW]",
        height=420,
        hovermode="x unified",
    )
    return fig


# ---------------------------------------------------------------------------
# Streamlit Main
# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="Deutschland-Netzkarte v2", layout="wide")

    st.title("Deutschland-Netzkarte - Entwurf v2")
    st.markdown(
        """
        4 Verbraucher-Cluster, 10 Uebertragungsleitungen, Erzeuger (Wind,
        PV, BESS, Konventionell) und 24h-Animation. Mit den Slidern in
        der Sidebar laesst sich Wind, PV und BESS zwischen 0 % und 300 %
        der heutigen installierten Leistung skalieren.

        > Hinweis: didaktische Lehrsimulation. Kein Lastfluss, keine
        > reale Netzdynamik. Werte gerundet und vereinfacht.
        """
    )

    # ---- Sidebar -----------------------------------------------------
    st.sidebar.header("Skalierung [%] (100 % = aktuelle DE-Werte)")
    wind_pct = st.sidebar.slider("Wind",       0, 300, 100, 5)
    pv_pct   = st.sidebar.slider("PV",         0, 300, 100, 5)
    bess_pct = st.sidebar.slider("BESS",       0, 300, 100, 5)
    load_pct = st.sidebar.slider("Last",      50, 200, 100, 5)
    soc_pct  = st.sidebar.slider("Start-SOC [%]", 0, 100, 50, 5)

    st.sidebar.caption(
        f"Referenz 100 %:\n"
        f"- Wind = {REF_WIND_GW:.0f} GW\n"
        f"- PV   = {REF_PV_GW:.0f} GW\n"
        f"- BESS = {REF_BESS_GW:.0f} GW / {REF_BESS_GWH:.0f} GWh\n"
        f"- Konv = {REF_KONV_GW:.0f} GW (fix)"
    )

    wind_scale = wind_pct / 100.0
    pv_scale   = pv_pct   / 100.0
    bess_scale = bess_pct / 100.0
    load_scale = load_pct / 100.0

    # ---- Daten + Simulation -----------------------------------------
    generators = get_generators()
    consumers  = get_consumer_clusters()
    lines      = get_lines(consumers)

    profiles = generate_profiles(wind_scale, pv_scale, bess_scale, load_scale)
    df = simulate_dispatch(profiles, bess_scale, soc_start_pct=soc_pct)

    # ---- 24h-Slider -------------------------------------------------
    st.subheader("Zeitslider (Stunde des Tages)")
    hour = st.slider("Stunde", 0, 23, 12, 1)

    hour_row = df.iloc[hour]

    # ---- Live-Kennzahlen --------------------------------------------
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Last [GW]",   f"{hour_row['Last_GW']:.1f}")
    k2.metric("Wind [GW]",   f"{hour_row['Wind_GW']:.1f}")
    k3.metric("PV [GW]",     f"{hour_row['PV_GW']:.1f}")
    k4.metric("BESS [GW]",   f"{hour_row['BESS_GW']:+.1f}")
    k5.metric("Konv. [GW]",  f"{hour_row['Konv_GW']:.1f}")

    k6, k7, k8 = st.columns(3)
    k6.metric("Netzbilanz [GW]", f"{hour_row['Netzbilanz_GW']:+.2f}")
    k7.metric("SOC [%]",          f"{hour_row['SOC_pct']:.1f}")
    k8.metric("Status",           hour_row["Status"])

    # ---- Karte ------------------------------------------------------
    st.subheader("Netzkarte (aktuelle Stunde)")
    fig_map = build_map(generators, consumers, lines, hour_row,
                        wind_scale, pv_scale, bess_scale)
    st.plotly_chart(fig_map, use_container_width=True)

    # ---- Stack-Balkendiagramm ---------------------------------------
    st.subheader("Erzeugungsmix vs. Last ueber 24 h")
    fig_stack = build_stack(df, highlight_hour=hour)
    st.plotly_chart(fig_stack, use_container_width=True)

    # ---- Tabellen ---------------------------------------------------
    with st.expander("Stuendliche Tabelle"):
        st.dataframe(
            df[[
                "Stunde", "Last_GW", "PV_GW", "Wind_GW",
                "Konv_GW", "BESS_GW", "SOC_GWh", "SOC_pct",
                "Netzbilanz_GW", "Status",
            ]].round(2),
            use_container_width=True,
        )
    with st.expander("Erzeuger-Standorte"):
        st.dataframe(generators, use_container_width=True)
    with st.expander("Verbraucher-Cluster"):
        st.dataframe(consumers, use_container_width=True)
    with st.expander("Leitungen"):
        st.dataframe(lines, use_container_width=True)

    st.caption(
        "Entwurfsstand v2. Slider Wind/PV/BESS skalieren die installierte "
        "Leistung relativ zu heutigen Referenzwerten (0 %..300 %). "
        "Konventionelle Leistung bleibt fix, kann aber spaeter ebenfalls "
        "skaliert werden. Leitungsauslastung ist ein didaktischer Proxy, "
        "keine echte Lastflussberechnung."
    )


if __name__ == "__main__":
    main()
