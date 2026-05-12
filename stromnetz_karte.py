# -*- coding: utf-8 -*-
"""
Streamlit App: Stromnetz Deutschland - Visualisierung
Knoten (Umspannwerke), Wind im Norden, Solar im Sueden, Verbraucher an den Raendern.
Drei Slider steuern Wind-, Solar- und Verbrauchsniveau.
"""

import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.lines import Line2D

# ============================================================
# Konfiguration
# ============================================================
st.set_page_config(page_title="Stromnetz Deutschland", layout="wide")
st.title("Stromnetz Deutschland - Visualisierung")
st.write("Wind (Norden), Solar (Sueden) und Verbraucher (Raender). "
         "Mit den Slidern links koennen Wind-, Solar- und Verbrauchsniveau eingestellt werden.")

# ============================================================
# Sidebar: Slider
# ============================================================
st.sidebar.header("Steuerung") 
wind_level = st.sidebar.slider("Wind", 0.0, 1.0, 0.2, 0.05,
                               help="Windstaerke / -einspeisung")
solar_level = st.sidebar.slider("Solar", 0.0, 1.0, 0.7, 0.05,
                                help="Sonneneinstrahlung / Solarerzeugung")
consumption_level = st.sidebar.slider("Verbrauch (consumption)", 0.0, 1.0, 0.1, 0.05,
                                      help="Lastniveau der Verbraucher")

st.sidebar.markdown("---")
zeige_flusspfeile = st.sidebar.checkbox("Lastfluss-Pfeile zeigen", value=True)
zeige_werte = st.sidebar.checkbox("Werte an Erzeugern/Verbrauchern", value=True)

# ============================================================
# Knoten (Umspannwerke / Staedte)
# Koordinaten in einem Karten-System x: 0-10, y: 0-12 (Norden oben)
# ============================================================
knoten = {
    "W": {"pos": (3.0, 8.5), "name": "West (Ruhrgebiet)"},
    "H": {"pos": (5.2, 9.5), "name": "Hamburg"},
    "B": {"pos": (7.5, 9.0), "name": "Berlin"},
    "R": {"pos": (3.5, 6.0), "name": "Rhein/Main"},
    "L": {"pos": (8.5, 6.0), "name": "Leipzig"},
    "M1": {"pos": (4.8, 4.0), "name": "Mannheim"},
    "S":  {"pos": (5.0, 2.5), "name": "Stuttgart"},
    "M2": {"pos": (7.0, 2.5), "name": "Muenchen"},
}

# Verbindungen (Hochspannungsleitungen)
leitungen = [
    ("W", "H"),
    ("W", "R"),
    ("H", "B"),
    ("H", "R"),
    ("H", "M1"),
    ("B", "R"),
    ("B", "L"),
    ("R", "M1"),
    ("R", "S"),
    ("L", "M2"),
    ("M1", "S"),
    ("M1", "M2"),
    ("S", "M2"),
]

# ============================================================
# Erzeuger und Verbraucher
# typ: "wind" (lila Dreieck), "solar" (gruenes Dreieck), "load" (gelbes Quadrat)
# pos: Position des Symbols
# anschluss: Knoten an den es angeschlossen ist
# kap: maximale Leistung
# ============================================================
einheiten = [
    # Wind im Norden (lila Dreiecke)
    {"typ": "wind", "pos": (1.8, 11.0), "anschluss": "W", "kap": 1.2, "label": "Wind NW"},
    {"typ": "wind", "pos": (2.8, 11.5), "anschluss": "W", "kap": 1.0, "label": "Wind W"},
    {"typ": "wind", "pos": (6.0, 11.5), "anschluss": "H", "kap": 1.5, "label": "Wind N"},
    {"typ": "wind", "pos": (7.8, 11.3), "anschluss": "B", "kap": 1.3, "label": "Wind NO"},

    # Solar im Sueden (gruene Dreiecke)
    {"typ": "solar", "pos": (5.6, 3.2), "anschluss": "M1", "kap": 1.2, "label": "Solar Bayern N"},
    {"typ": "solar", "pos": (6.5, 3.2), "anschluss": "M2", "kap": 1.4, "label": "Solar Bayern O"},
    {"typ": "solar", "pos": (6.2, 1.8), "anschluss": "M2", "kap": 1.3, "label": "Solar Bayern S"},

    # Verbraucher (gelbe Quadrate) an den Raendern
    {"typ": "load", "pos": (5.0, 11.7), "anschluss": "H",  "kap": 1.5, "label": "Last Hamburg"},
    {"typ": "load", "pos": (1.5, 6.0), "anschluss": "R",  "kap": 1.8, "label": "Last West"},
    {"typ": "load", "pos": (10.0, 6.0), "anschluss": "L",  "kap": 1.4, "label": "Last Ost"},
    {"typ": "load", "pos": (5.0, 0.5), "anschluss": "S",  "kap": 1.6, "label": "Last Sued"},
]

# ============================================================
# Hilfsfunktion: Deutschland-Umriss (sehr grob, nur Rahmen)
# ============================================================
def zeichne_de_umriss(ax):
    umriss_pts = np.array([
        (3.0, 11.8), (4.0, 12.0), (5.0, 11.8), (6.5, 12.0), (7.5, 11.5),
        (8.5, 11.0), (8.7, 10.0), (9.0, 9.0), (9.3, 7.5), (9.0, 6.5),
        (9.5, 5.5), (9.0, 4.5), (8.0, 3.5), (7.5, 2.0), (6.5, 0.8),
        (5.5, 0.4), (4.5, 0.6), (3.5, 1.2), (2.8, 2.5), (2.5, 4.0),
        (1.8, 5.0), (1.5, 6.5), (2.0, 7.5), (2.2, 8.5), (2.5, 9.5),
        (2.8, 10.5), (3.0, 11.8),
    ])
    poly = patches.Polygon(umriss_pts, closed=True,
                           facecolor="#fafafa", edgecolor="#9e9e9e",
                           lw=1.2, zorder=0)
    ax.add_patch(poly)

# ============================================================
# Berechnung von Erzeugung und Verbrauch
# ============================================================
def berechne_werte(wind, solar, last):
    erz_solar, erz_wind, verbrauch = 0.0, 0.0, 0.0
    werte = []
    for e in einheiten:
        if e["typ"] == "wind":
            v = e["kap"] * wind
            erz_wind += v
        elif e["typ"] == "solar":
            v = e["kap"] * solar
            erz_solar += v
        else:
            v = e["kap"] * last
            verbrauch += v
        werte.append(v)
    return werte, erz_wind, erz_solar, verbrauch

# ============================================================
# Zeichnen
# ============================================================
def zeichne_karte(wind, solar, last):
    fig, ax = plt.subplots(figsize=(11, 11))
    zeichne_de_umriss(ax)

    werte, erz_wind, erz_solar, verbrauch = berechne_werte(wind, solar, last)

    bilanz = (erz_wind + erz_solar) - verbrauch
    leitung_farbe = "#1a1a1a"
    leitung_breite = 2.0 + min(abs(bilanz) * 0.6, 3.0)

    # ---- Leitungen zwischen Knoten ----
    for a, b in leitungen:
        x1, y1 = knoten[a]["pos"]
        x2, y2 = knoten[b]["pos"]
        ax.plot([x1, x2], [y1, y2], color=leitung_farbe,
                lw=leitung_breite, zorder=2, solid_capstyle="round")

        if zeige_flusspfeile and abs(bilanz) > 0.05:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            if bilanz > 0:
                # Norden -> Sueden
                if y1 > y2:
                    dx, dy = (x2 - x1) * 0.12, (y2 - y1) * 0.12
                else:
                    dx, dy = (x1 - x2) * 0.12, (y1 - y2) * 0.12
            else:
                # Sueden -> Norden
                if y1 < y2:
                    dx, dy = (x2 - x1) * 0.12, (y2 - y1) * 0.12
                else:
                    dx, dy = (x1 - x2) * 0.12, (y1 - y2) * 0.12
            ax.annotate("", xy=(mx + dx, my + dy), xytext=(mx - dx, my - dy),
                        arrowprops=dict(arrowstyle="->", color="#d32f2f", lw=2.0),
                        zorder=4)

    # ---- Stichleitungen Erzeuger/Verbraucher -> Knoten ----
    for e in einheiten:
        x1, y1 = e["pos"]
        x2, y2 = knoten[e["anschluss"]]["pos"]
        ax.plot([x1, x2], [y1, y2], color="#1a1a1a", lw=1.6,
                zorder=1, solid_capstyle="round")

    # ---- Erzeuger / Verbraucher zeichnen ----
    for e, v in zip(einheiten, werte):
        x, y = e["pos"]
        anteil = v / max(e["kap"], 1e-6)
        if e["typ"] == "wind":
            size = 600 + 1400 * anteil
            ax.scatter(x, y, s=size, c="#9c27b0", marker="^",
                       edgecolors="#4a148c", lw=1.5, zorder=5)
        elif e["typ"] == "solar":
            size = 600 + 1400 * anteil
            ax.scatter(x, y, s=size, c="#43a047", marker="^",
                       edgecolors="#1b5e20", lw=1.5, zorder=5)
        else:
            size_box = 0.55 + 0.6 * anteil
            rect = patches.Rectangle((x - size_box / 2, y - size_box / 2),
                                     size_box, size_box,
                                     facecolor="#fdd835",
                                     edgecolor="#f57f17", lw=1.5, zorder=5)
            ax.add_patch(rect)

        if zeige_werte:
            ax.text(x, y - 0.55, f"{v:.2f}", ha="center", va="top",
                    fontsize=8, color="#333", zorder=6)

    # ---- Knoten zeichnen (blaue Kreise mit Buchstaben) ----
    for k, info in knoten.items():
        x, y = info["pos"]
        label = k[0]
        circ = patches.Circle((x, y), 0.32, facecolor="#1f5f8b",
                              edgecolor="#0d3a5c", lw=1.5, zorder=7)
        ax.add_patch(circ)
        ax.text(x, y, label, ha="center", va="center",
                color="white", fontsize=12, fontweight="bold", zorder=8)

    ax.set_xlim(0, 11)
    ax.set_ylim(-0.5, 12.5)
    ax.set_aspect("equal")
    ax.axis("off")

    legend_elements = [
        Line2D([0], [0], marker="^", color="w", markerfacecolor="#9c27b0",
               markeredgecolor="#4a148c", markersize=15, label="Wind"),
        Line2D([0], [0], marker="^", color="w", markerfacecolor="#43a047",
               markeredgecolor="#1b5e20", markersize=15, label="Solar"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#fdd835",
               markeredgecolor="#f57f17", markersize=15, label="Verbraucher"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#1f5f8b",
               markeredgecolor="#0d3a5c", markersize=12, label="Umspannwerk"),
        Line2D([0], [0], color="#1a1a1a", lw=2.5, label="Leitung"),
    ]
    if zeige_flusspfeile:
        legend_elements.append(
            Line2D([0], [0], color="#d32f2f", lw=2.0, label="Lastfluss")
        )
    ax.legend(handles=legend_elements, loc="upper left", fontsize=10,
              framealpha=0.95)

    plt.tight_layout()
    return fig, erz_wind, erz_solar, verbrauch

# ============================================================
# Anzeige
# ============================================================
fig, erz_wind, erz_solar, verbrauch = zeichne_karte(
    wind_level, solar_level, consumption_level
)

col_karte, col_info = st.columns([3, 1])

with col_karte:
    st.pyplot(fig)
    plt.close(fig)

with col_info:
    st.subheader("Bilanz")
    erz_gesamt = erz_wind + erz_solar
    bilanz = erz_gesamt - verbrauch

    st.metric("Wind", f"{erz_wind:.2f}")
    st.metric("Solar", f"{erz_solar:.2f}")
    st.metric("Erzeugung gesamt", f"{erz_gesamt:.2f}")
    st.metric("Verbrauch", f"{verbrauch:.2f}")
    st.metric("Bilanz", f"{bilanz:+.2f}",
              delta="Ueberschuss" if bilanz > 0 else "Defizit",
              delta_color="normal" if bilanz > 0 else "inverse")

    st.markdown("---")
    if bilanz > 0:
        st.success(f"Netzueberschuss: {bilanz:.2f}\n\n"
                   "Strom fliesst tendenziell von Norden (Wind) nach Sueden.")
    elif bilanz < 0:
        st.warning(f"Netzdefizit: {bilanz:.2f}\n\n"
                   "Verbrauch uebersteigt erneuerbare Erzeugung. "
                   "Backup/Import noetig.")
    else:
        st.info("Erzeugung und Verbrauch sind ausgeglichen.")

st.markdown("---")
st.caption("Hinweis: Schematische Visualisierung. Knotenbuchstaben: "
           "W=West/Ruhr, H=Hamburg, B=Berlin, R=Rhein/Main, L=Leipzig, "
           "M=Mannheim/Muenchen, S=Stuttgart.")
