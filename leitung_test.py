# -*- coding: utf-8 -*-
"""
Streamlit App: Einfache Leitungs-Visualisierung
Eine horizontale Leitung mit mehreren Einspeisern und einer Last.
Lastfluss wird als Pfeile auf den Leitungssegmenten dargestellt.
"""

import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.lines import Line2D

# ============================================================
# Konfiguration
# ============================================================
st.set_page_config(page_title="Leitung Test", layout="wide")
st.title("Leitung mit Einspeisern und Last")
st.write("Einfache horizontale Leitung. Slider links steuern die Einspeiser "
         "und die Last. Lastfluss-Pfeile zeigen Richtung und Staerke.")

# ============================================================
# Sidebar: Einspeiser und Last
# ============================================================
st.sidebar.header("Einspeiser")
gen1 = st.sidebar.slider("Einspeiser 1 (Wind)", 0.0, 2.0, 0.8, 0.1)
gen2 = st.sidebar.slider("Einspeiser 2 (Solar)", 0.0, 2.0, 1.2, 0.1)
gen3 = st.sidebar.slider("Einspeiser 3 (Bio)", 0.0, 2.0, 0.4, 0.1)

st.sidebar.header("Verbraucher")
last = st.sidebar.slider("Last", 0.0, 5.0, 2.0, 0.1)

st.sidebar.markdown("---")
zeige_pfeile = st.sidebar.checkbox("Lastfluss-Pfeile zeigen", value=True)
zeige_werte = st.sidebar.checkbox("Werte anzeigen", value=True)

# ============================================================
# Layout der Leitung
# Knoten auf der Leitung von links nach rechts:
#   N1 (Gen1) --- N2 (Gen2) --- N3 (Gen3) --- N4 (Last)
# ============================================================
# x-Position der Knoten
knoten_x = {
    "N1": 1.0,
    "N2": 4.0,
    "N3": 7.0,
    "N4": 10.0,
}
y_leitung = 2.0  # Hoehe der Leitung

# Einspeiser/Verbraucher mit ihrem Wert und Anschlussknoten
einheiten = [
    {"typ": "gen",  "name": "G1 (Wind)",  "knoten": "N1", "wert": gen1, "farbe": "#9c27b0"},
    {"typ": "gen",  "name": "G2 (Solar)", "knoten": "N2", "wert": gen2, "farbe": "#43a047"},
    {"typ": "gen",  "name": "G3 (Bio)",   "knoten": "N3", "wert": gen3, "farbe": "#1565c0"},
    {"typ": "load", "name": "Last",       "knoten": "N4", "wert": last, "farbe": "#fdd835"},
]

# ============================================================
# Lastfluss-Berechnung (sehr vereinfacht, eindimensional)
# Alle Generatoren speisen am jeweiligen Knoten ein, die Last sitzt rechts.
# Der Fluss durch ein Leitungssegment = Summe der Einspeisungen links davon
#   minus Summe der Lasten links davon.
# Positiv = Fluss nach rechts, negativ = nach links.
# ============================================================
reihenfolge = ["N1", "N2", "N3", "N4"]
einspeisung_an = {k: 0.0 for k in reihenfolge}
last_an = {k: 0.0 for k in reihenfolge}
for e in einheiten:
    if e["typ"] == "gen":
        einspeisung_an[e["knoten"]] += e["wert"]
    else:
        last_an[e["knoten"]] += e["wert"]

# Fluss durch Segment i->i+1
fluesse = []
kumuliert = 0.0
for i in range(len(reihenfolge) - 1):
    k = reihenfolge[i]
    kumuliert += einspeisung_an[k] - last_an[k]
    fluesse.append(kumuliert)

# ============================================================
# Zeichnen
# ============================================================
fig, ax = plt.subplots(figsize=(12, 5))
fig.patch.set_alpha(0.0)   # transparenter Hintergrund Figure
ax.set_facecolor("none")   # transparenter Hintergrund Achse

# ---- Leitungssegmente ----
max_fluss = max([abs(f) for f in fluesse] + [0.5])
for i, f in enumerate(fluesse):
    x1 = knoten_x[reihenfolge[i]]
    x2 = knoten_x[reihenfolge[i + 1]]
    breite = 2.0 + 4.0 * (abs(f) / max_fluss)
    ax.plot([x1, x2], [y_leitung, y_leitung],
            color="#1a1a1a", lw=breite, solid_capstyle="round", zorder=2)

    # Pfeil in Flussrichtung
    if zeige_pfeile and abs(f) > 0.05:
        mx = (x1 + x2) / 2
        if f > 0:
            xa, xb = mx - 0.5, mx + 0.5  # nach rechts
        else:
            xa, xb = mx + 0.5, mx - 0.5  # nach links
        ax.annotate("", xy=(xb, y_leitung), xytext=(xa, y_leitung),
                    arrowprops=dict(arrowstyle="->", color="#d32f2f", lw=2.5),
                    zorder=4)
        ax.text(mx, y_leitung + 0.35, f"{f:+.2f}",
                ha="center", va="bottom", fontsize=10, color="#d32f2f",
                fontweight="bold", zorder=5)

# ---- Knoten zeichnen ----
for k in reihenfolge:
    x = knoten_x[k]
    circ = patches.Circle((x, y_leitung), 0.18,
                          facecolor="#1f5f8b", edgecolor="#0d3a5c",
                          lw=1.5, zorder=6)
    ax.add_patch(circ)
    ax.text(x, y_leitung, k, ha="center", va="center", color="white",
            fontsize=9, fontweight="bold", zorder=7)

# ---- Einspeiser und Last zeichnen ----
for e in einheiten:
    x = knoten_x[e["knoten"]]
    if e["typ"] == "gen":
        # Einspeiser oberhalb der Leitung als Dreieck
        y_sym = y_leitung + 1.2
        anteil = min(e["wert"] / 2.0, 1.0)
        size = 400 + 1500 * anteil
        ax.scatter(x, y_sym, s=size, c=e["farbe"], marker="^",
                   edgecolors="black", lw=1.2, zorder=5)
        # Stichleitung
        ax.plot([x, x], [y_leitung, y_sym - 0.15], color="#1a1a1a",
                lw=1.5, zorder=1)
        # Beschriftung
        ax.text(x, y_sym + 0.5, e["name"], ha="center", va="bottom",
                fontsize=10, fontweight="bold")
        if zeige_werte:
            ax.text(x, y_sym - 0.05, f"{e['wert']:.2f}",
                    ha="center", va="center", fontsize=9, color="white",
                    fontweight="bold", zorder=6)
    else:
        # Last unterhalb der Leitung als gelbes Quadrat
        y_sym = y_leitung - 1.2
        anteil = min(e["wert"] / 5.0, 1.0)
        groesse = 0.35 + 0.45 * anteil
        rect = patches.Rectangle((x - groesse / 2, y_sym - groesse / 2),
                                 groesse, groesse,
                                 facecolor=e["farbe"], edgecolor="#f57f17",
                                 lw=1.5, zorder=5)
        ax.add_patch(rect)
        ax.plot([x, x], [y_leitung, y_sym + groesse / 2], color="#1a1a1a",
                lw=1.5, zorder=1)
        ax.text(x, y_sym - 0.55, e["name"], ha="center", va="top",
                fontsize=10, fontweight="bold")
        if zeige_werte:
            ax.text(x, y_sym, f"{e['wert']:.2f}",
                    ha="center", va="center", fontsize=9, color="black",
                    fontweight="bold", zorder=6)

# ---- Achsen ----
ax.set_xlim(0, 11)
ax.set_ylim(-0.5, 4.5)
ax.set_aspect("equal")
ax.axis("off")

# ---- Legende ----
legend_elements = [
    Line2D([0], [0], marker="^", color="w", markerfacecolor="#9c27b0",
           markeredgecolor="black", markersize=14, label="Einspeiser"),
    Line2D([0], [0], marker="s", color="w", markerfacecolor="#fdd835",
           markeredgecolor="#f57f17", markersize=14, label="Verbraucher"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor="#1f5f8b",
           markeredgecolor="#0d3a5c", markersize=12, label="Knoten"),
    Line2D([0], [0], color="#1a1a1a", lw=3, label="Leitung"),
]
if zeige_pfeile:
    legend_elements.append(
        Line2D([0], [0], color="#d32f2f", lw=2.5, label="Lastfluss")
    )
ax.legend(handles=legend_elements, loc="upper right", fontsize=10,
          framealpha=0.95)

plt.tight_layout()

# ============================================================
# Anzeige
# ============================================================
col_plot, col_info = st.columns([3, 1])

with col_plot:
    st.pyplot(fig, transparent=True)
    plt.close(fig)

with col_info:
    st.subheader("Bilanz")
    erz_gesamt = gen1 + gen2 + gen3
    bilanz = erz_gesamt - last
    st.metric("Einspeisung gesamt", f"{erz_gesamt:.2f}")
    st.metric("Last", f"{last:.2f}")
    st.metric("Bilanz", f"{bilanz:+.2f}",
              delta="Ueberschuss" if bilanz > 0 else "Defizit",
              delta_color="normal" if bilanz > 0 else "inverse")

    st.markdown("---")
    st.subheader("Segmentfluesse")
    for i, f in enumerate(fluesse):
        a = reihenfolge[i]
        b = reihenfolge[i + 1]
        richtung = "->" if f > 0 else ("<-" if f < 0 else "--")
        st.write(f"{a} {richtung} {b}: **{f:+.2f}**")

st.caption("Positiver Fluss = Strom fliesst nach rechts, negativ nach links. "
           "Die Liniendicke skaliert mit der Stromstaerke im Segment.")
