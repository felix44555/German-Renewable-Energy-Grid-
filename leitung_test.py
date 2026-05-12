"""
Deutschlandkarte_Netz.py
========================
Vereinfachte interaktive Deutschland-Karte mit:
  - Wind-Erzeugern (vorwiegend Nord/Offshore)
  - PV-Erzeugern (vorwiegend Sued/Mitte)
  - BESS (Batteriespeicher, verteilt)
  - Restlichen konventionellen Erzeugern (Gas/Kohle/Wasser/Biomasse)
  - 8 Verbraucher-Clustern (Ballungsraeume)
  - Vereinfachten Uebertragungslinien

Hinweis: ENTWURF / didaktische Lehrsimulation.
Kein reales Netzmodell, keine Lastflussrechnung.

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
# Stammdaten: Erzeuger und Verbraucher
# ---------------------------------------------------------------------------
# Koordinaten (lat, lon) sind grob in Deutschland verortet.

def get_generators() -> pd.DataFrame:
    """Liste vereinfachter Erzeuger-Standorte mit Typ und Leistung [GW]."""
    data = [
        # Wind Offshore Nord/Ostsee
        ("Wind Offshore Nordsee", "Wind", 54.5, 7.5, 8.5),
        ("Wind Offshore Ostsee", "Wind", 54.6, 13.0, 3.5),
        # Wind Onshore Norden
        ("Wind Schleswig-Holstein", "Wind", 54.2, 9.5, 7.0),
        ("Wind Niedersachsen", "Wind", 52.8, 9.0, 12.5),
        ("Wind Brandenburg", "Wind", 52.4, 13.0, 8.5),
        ("Wind Sachsen-Anhalt", "Wind", 51.9, 11.6, 5.5),
        # PV Sueden/Mitte
        ("PV Bayern", "PV", 48.9, 11.4, 22.0),
        ("PV Baden-Wuerttemberg", "PV", 48.7, 9.2, 9.5),
        ("PV NRW", "PV", 51.4, 7.5, 8.0),
        ("PV Hessen", "PV", 50.5, 9.0, 4.5),
        # Konventionelle / Sonstige
        ("Gas/Kohle Ruhrgebiet", "Konventionell", 51.5, 7.0, 12.0),
        ("Gas Sueddeutschland", "Konventionell", 48.5, 11.5, 6.5),
        ("Biomasse/Wasser Sued", "Konventionell", 47.7, 10.5, 3.0),
        ("Gas Berlin/Brandenburg", "Konventionell", 52.5, 13.4, 4.0),
        # BESS-Standorte (verteilt)
        ("BESS Nord", "BESS", 53.5, 9.9, 2.5),
        ("BESS West", "BESS", 51.2, 6.8, 3.0),
        ("BESS Mitte", "BESS", 50.3, 10.0, 2.0),
        ("BESS Sued", "BESS", 48.5, 11.5, 2.5),
    ]
    return pd.DataFrame(
        data, columns=["Name", "Typ", "lat", "lon", "Leistung_GW"]
    )


def get_consumer_clusters() -> pd.DataFrame:
    """8 vereinfachte Verbraucher-Cluster (Ballungsraeume)."""
    data = [
        ("Hamburg/Nord",            53.55, 10.00, 7.5),
        ("Berlin/Brandenburg",      52.52, 13.40, 9.0),
        ("Ruhrgebiet/NRW",          51.45,  7.20, 18.0),
        ("Rhein-Main",              50.10,  8.70, 10.5),
        ("Rhein-Neckar/Stuttgart",  48.78,  9.18, 11.0),
        ("Muenchen/Suedbayern",     48.14, 11.58, 10.0),
        ("Leipzig/Sachsen",         51.34, 12.37,  6.0),
        ("Hannover/Niedersachsen",  52.37,  9.73,  6.5),
    ]
    return pd.DataFrame(
        data, columns=["Cluster", "lat", "lon", "Last_GW"]
    )


def get_lines(generators: pd.DataFrame, consumers: pd.DataFrame) -> list[dict]:
    """
    Vereinfachte Uebertragungslinien als Liste von Verbindungen
    (Erzeuger -> Cluster). Stark vereinfacht, nur didaktisch.
    """
    # Mapping: (Erzeuger-Name, Cluster-Name)
    pairs = [
        ("Wind Offshore Nordsee", "Hamburg/Nord"),
        ("Wind Offshore Nordsee", "Ruhrgebiet/NRW"),
        ("Wind Offshore Ostsee", "Berlin/Brandenburg"),
        ("Wind Schleswig-Holstein", "Hamburg/Nord"),
        ("Wind Niedersachsen", "Hannover/Niedersachsen"),
        ("Wind Niedersachsen", "Ruhrgebiet/NRW"),
        ("Wind Brandenburg", "Berlin/Brandenburg"),
        ("Wind Sachsen-Anhalt", "Leipzig/Sachsen"),
        ("PV Bayern", "Muenchen/Suedbayern"),
        ("PV Baden-Wuerttemberg", "Rhein-Neckar/Stuttgart"),
        ("PV NRW", "Ruhrgebiet/NRW"),
        ("PV Hessen", "Rhein-Main"),
        ("Gas/Kohle Ruhrgebiet", "Ruhrgebiet/NRW"),
        ("Gas Sueddeutschland", "Muenchen/Suedbayern"),
        ("Biomasse/Wasser Sued", "Rhein-Neckar/Stuttgart"),
        ("Gas Berlin/Brandenburg", "Berlin/Brandenburg"),
        ("BESS Nord", "Hamburg/Nord"),
        ("BESS West", "Ruhrgebiet/NRW"),
        ("BESS Mitte", "Rhein-Main"),
        ("BESS Sued", "Muenchen/Suedbayern"),
        # Nord-Sued-Trassen (vereinfachte HGUe-Anlehnung)
        ("Wind Niedersachsen", "Muenchen/Suedbayern"),
        ("Wind Schleswig-Holstein", "Rhein-Neckar/Stuttgart"),
    ]

    lines = []
    for gen_name, cl_name in pairs:
        g = generators[generators["Name"] == gen_name].iloc[0]
        c = consumers[consumers["Cluster"] == cl_name].iloc[0]
        lines.append(
            dict(
                gen=gen_name,
                cluster=cl_name,
                lat0=g["lat"], lon0=g["lon"],
                lat1=c["lat"], lon1=c["lon"],
                typ=g["Typ"],
            )
        )
    return lines


# ---------------------------------------------------------------------------
# Farb- und Symbolzuordnung
# ---------------------------------------------------------------------------
TYP_COLORS = {
    "Wind":          "#1f77b4",   # blau
    "PV":            "#ff7f0e",   # orange
    "BESS":          "#2ca02c",   # gruen
    "Konventionell": "#7f7f7f",   # grau
    "Verbraucher":   "#d62728",   # rot
}

TYP_SYMBOLS = {
    "Wind":          "triangle-up",
    "PV":            "square",
    "BESS":          "diamond",
    "Konventionell": "circle",
    "Verbraucher":   "star",
}


# ---------------------------------------------------------------------------
# Plot-Aufbau
# ---------------------------------------------------------------------------
def build_map(
    generators: pd.DataFrame,
    consumers: pd.DataFrame,
    lines: list[dict],
    show_types: set[str],
    show_lines: bool,
) -> go.Figure:
    """Erzeugt die Plotly-Karte (scattergeo)."""
    fig = go.Figure()

    # ---- Linien zuerst (damit Marker darueber liegen) -------------------
    if show_lines:
        for line in lines:
            if line["typ"] not in show_types:
                continue
            fig.add_trace(
                go.Scattergeo(
                    lon=[line["lon0"], line["lon1"]],
                    lat=[line["lat0"], line["lat1"]],
                    mode="lines",
                    line=dict(width=1.2, color=TYP_COLORS[line["typ"]]),
                    opacity=0.55,
                    hoverinfo="text",
                    text=f"{line['gen']} -> {line['cluster']}",
                    showlegend=False,
                )
            )

    # ---- Erzeuger ------------------------------------------------------
    for typ in ["Wind", "PV", "BESS", "Konventionell"]:
        if typ not in show_types:
            continue
        sub = generators[generators["Typ"] == typ]
        if sub.empty:
            continue
        fig.add_trace(
            go.Scattergeo(
                lon=sub["lon"],
                lat=sub["lat"],
                text=[
                    f"<b>{n}</b><br>Typ: {t}<br>Leistung: {p:.1f} GW"
                    for n, t, p in zip(sub["Name"], sub["Typ"], sub["Leistung_GW"])
                ],
                hoverinfo="text",
                mode="markers",
                name=typ,
                marker=dict(
                    size=8 + sub["Leistung_GW"] * 1.6,
                    color=TYP_COLORS[typ],
                    symbol=TYP_SYMBOLS[typ],
                    line=dict(width=1, color="black"),
                    opacity=0.9,
                ),
            )
        )

    # ---- Verbraucher-Cluster ------------------------------------------
    if "Verbraucher" in show_types:
        fig.add_trace(
            go.Scattergeo(
                lon=consumers["lon"],
                lat=consumers["lat"],
                text=[
                    f"<b>{c}</b><br>Last: {l:.1f} GW"
                    for c, l in zip(consumers["Cluster"], consumers["Last_GW"])
                ],
                hoverinfo="text",
                mode="markers+text",
                name="Verbraucher-Cluster",
                textposition="top center",
                textfont=dict(size=10, color="black"),
                marker=dict(
                    size=12 + consumers["Last_GW"] * 1.2,
                    color=TYP_COLORS["Verbraucher"],
                    symbol=TYP_SYMBOLS["Verbraucher"],
                    line=dict(width=1.2, color="black"),
                    opacity=0.9,
                ),
            )
        )

    # ---- Geo-Layout auf Deutschland --------------------------------
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
        title="Vereinfachte Deutschland-Karte: Erzeuger, BESS, Verbraucher",
        height=720,
        margin=dict(l=0, r=0, t=60, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=-0.05, x=0.5, xanchor="center"),
    )

    return fig


# ---------------------------------------------------------------------------
# Kennzahlen
# ---------------------------------------------------------------------------
def compute_overview(generators: pd.DataFrame, consumers: pd.DataFrame) -> dict:
    by_typ = generators.groupby("Typ")["Leistung_GW"].sum().to_dict()
    return {
        "summe_wind":   by_typ.get("Wind", 0.0),
        "summe_pv":     by_typ.get("PV", 0.0),
        "summe_bess":   by_typ.get("BESS", 0.0),
        "summe_konv":   by_typ.get("Konventionell", 0.0),
        "summe_last":   float(consumers["Last_GW"].sum()),
        "n_cluster":    len(consumers),
        "n_erzeuger":   len(generators),
    }


# ---------------------------------------------------------------------------
# Streamlit Main
# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="Deutschland-Netzkarte (Entwurf)", layout="wide")

    st.title("Deutschland-Netzkarte - Entwurf")
    st.markdown(
        """
        Vereinfachte Darstellung der wichtigsten Erzeugungsarten und
        Verbraucher-Cluster in Deutschland. **Dies ist ein Entwurf** zur
        spaeteren Kopplung mit dem 24h-Dispatch-Modell.

        > Hinweis: Kein reales Netzmodell. Keine Lastflussrechnung.
        > Standorte und Leistungen sind didaktisch gesetzte Beispielwerte.
        """
    )

    # ---- Sidebar -----------------------------------------------------
    st.sidebar.header("Anzeige")
    show_wind = st.sidebar.checkbox("Wind",            value=True)
    show_pv = st.sidebar.checkbox("PV",                value=True)
    show_bess = st.sidebar.checkbox("BESS",            value=True)
    show_konv = st.sidebar.checkbox("Konventionell",   value=True)
    show_verb = st.sidebar.checkbox("Verbraucher",     value=True)
    show_lines = st.sidebar.checkbox("Uebertragungslinien", value=True)

    show_types = set()
    if show_wind:  show_types.add("Wind")
    if show_pv:    show_types.add("PV")
    if show_bess:  show_types.add("BESS")
    if show_konv:  show_types.add("Konventionell")
    if show_verb:  show_types.add("Verbraucher")

    # ---- Daten -------------------------------------------------------
    generators = get_generators()
    consumers = get_consumer_clusters()
    lines = get_lines(generators, consumers)

    # ---- Kennzahlen --------------------------------------------------
    info = compute_overview(generators, consumers)
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Wind [GW]",          f"{info['summe_wind']:.1f}")
    k2.metric("PV [GW]",            f"{info['summe_pv']:.1f}")
    k3.metric("BESS [GW]",          f"{info['summe_bess']:.1f}")
    k4.metric("Konventionell [GW]", f"{info['summe_konv']:.1f}")
    k5.metric("Last gesamt [GW]",   f"{info['summe_last']:.1f}")

    # ---- Karte -------------------------------------------------------
    fig = build_map(generators, consumers, lines, show_types, show_lines)
    st.plotly_chart(fig, use_container_width=True)

    # ---- Tabellen ----------------------------------------------------
    with st.expander("Erzeuger-Tabelle"):
        st.dataframe(generators, use_container_width=True)
    with st.expander("Verbraucher-Cluster-Tabelle"):
        st.dataframe(consumers, use_container_width=True)

    st.caption(
        "Entwurfsstand: statische Standorte, statische Leistungen. "
        "Im naechsten Schritt koennen Erzeuger an das 24h-Dispatch-Modell "
        "gekoppelt werden, um Flussrichtungen und Auslastung der Linien "
        "zeitabhaengig darzustellen."
    )


if __name__ == "__main__":
    main()
