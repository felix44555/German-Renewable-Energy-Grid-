# -*- coding: utf-8 -*-
"""
Streamlit App: Einfache Leitungs-Visualisierung
Eine horizontale Leitung mit Einspeisern (Wind, Solar, weitere EE) und Last.
Slider in Prozent (0-100%) der installierten Kapazitaet.
Reale installierte Leistung in Deutschland (Stand Anfang 2026):
  - Wind:          ca. 75 GW (64 GW onshore + ~10 GW offshore)
  - Solar (PV):    ca. 100 GW
  - Weitere EE:    ca. 14 GW (Wasserkraft ~5 GW + Biomasse ~9 GW + Geothermie/sonst.)
  - Spitzenlast:   ca. 80 GW (typischer Wintermittag)
Quelle: BNetzA Marktstammdatenregister / Fraunhofer ISE (Naeherungswerte).
"""

import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.lines import Line2D

# ============================================================
# Reale Referenzkapazitaeten Deutschland (GW)
# ============================================================
KAP_WIND_GW    = 75.0   # Wind onshore + offshore
KAP_SOLAR_GW   = 100.0  # Photovoltaik
KAP_WEITERE_GW = 14.0   # Wasserkraft + Biomasse + sonstige EE
LAST_MAX_GW    = 80.0   # typische Spitzenlast Deutschland

# ============================================================
# Konfiguration
# ============================================================
st.set_page_config(page_title="Leitung Test", layout="wide")
st.title("Leitung mit Einspeisern und Last - Deutschland")
st.write("Slider in Prozent der installierten Kapazitaet. "
         "Daneben wird die aktuelle Leistung in GW angezeigt.")

# ============================================================
# Sidebar: Einspeiser (in Prozent) und Last
# ============================================================
st.sidebar.header("Einspeiser (% der installierten Leistung)")
wind_pct = st.sidebar.slider(
    f"Wind  (max {KAP_WIND_GW:.0f} GW)",
    0, 100, 25, 1
)
solar_pct = st.sidebar.slider(
    f"Solar  (max {KAP_SOLAR_GW:.0f} GW)",
    0, 100, 60, 1
)
weitere_pct = st.sidebar.slider(
    f"Weitere EE  (max {KAP_WEITERE_GW:.0f} GW)",
    0, 100, 70, 1,
    help="Wasserkraft + Biomasse + sonstige Erneuerbare"
)

st.sidebar.header("Verbraucher")
last_pct = st.sidebar.slider(
    f"Last  (max {LAST_MAX_GW:.0f} GW)",
    0, 100, 70, 1
)

st.sidebar.markdown("---")
zeige_pfeile = st.sidebar.checkbox("Lastfluss-Pfeile zeigen", value=True)
zeige_werte = st.sidebar.checkbox("Werte (GW) anzeigen", value=True)

# ============================================================
# Aktuelle Leistung in GW berechnen
# ============================================================
gen_wind_gw    = KAP_WIND_GW    * wind_pct    / 100.0
gen_solar_gw   = KAP_SOLAR_GW   * solar_pct   / 100.0
gen_weitere_gw = KAP_WEITERE_GW * weitere_pct / 100.0
last_gw        = LAST_MAX_GW    * last_pct    / 100.0

# ============================================================
# Layout der Leitung
# Knoten: N1 (Wind) -- N2 (Solar) -- N3 (Weitere EE) -- N4 (Last)
# ============================================================
knoten_x = {"N1": 1.0, "N2": 4.0, "N3": 7.0, "N4": 10.0}
y_leitung = 2.0

einheiten = [
    {"typ": "gen",  "name": "Wind",       "knoten": "N1",
     "wert": gen_wind_gw,    "kap": KAP_WIND_GW,    "farbe": "#9c27b0"},
    {"typ": "gen",  "name": "Solar",      "knoten": "N2",
     "wert": gen_solar_gw,   "kap": KAP_SOLAR_GW,   "farbe": "#43a047"},
    {"typ": "gen",  "name": "Weitere EE", "knoten": "N3",
     "wert": gen_weitere_gw, "kap": KAP_WEITERE_GW, "farbe": "#1565c0"},
    {"typ": "load", "name": "Last",       "knoten": "N4",
     "wert": last_gw,        "kap": LAST_MAX_GW,    "farbe": "#fdd835"},
]

# ============================================================
# Lastfluss (eindimensional, vereinfacht)
# Fluss durch Segment i->i+1 = Summe Einspeisung links - Summe Last links
# Positiv = nach rechts, negativ = nach links
# ============================================================
reihenfolge = ["N1", "N2", "N3", "N4"]
einspeisung_an = {k: 0.0 for k in reihenfolge}
last_an = {k: 0.0 for k in reihenfolge}
for e in einheiten:
    if e["typ"] == "gen":
        einspeisung_an[e["knoten"]] += e["wert"]
    else:
        last_an[e["knoten"]] += e["wert"]

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
fig.patch.set_alpha(0.0)
ax.set_facecolor("none")

# ---- Leitungssegmente ----
max_fluss = max([abs(f) for f in fluesse] + [1.0])
for i, f in enumerate(fluesse):
    x1 = knoten_x[reihenfolge[i]]
    x2 = knoten_x[reihenfolge[i + 1]]
    breite = 2.0 + 4.0 * (abs(f) / max_fluss)
    ax.plot([x1, x2], [y_leitung, y_leitung],
            color="#1a1a1a", lw=breite, solid_capstyle="round", zorder=2)

    if zeige_pfeile and abs(f) > 0.5:  # > 0.5 GW
        mx = (x1 + x2) / 2
        if f > 0:
            xa, xb = mx - 0.5, mx + 0.5
        else:
            xa, xb = mx + 0.5, mx - 0.5
        ax.annotate("", xy=(xb, y_leitung), xytext=(xa, y_leitung),
                    arrowprops=dict(arrowstyle="->", color="#d32f2f", lw=2.5),
                    zorder=4)
        ax.text(mx, y_leitung + 0.35, f"{f:+.1f} GW",
                ha="center", va="bottom", fontsize=10, color="#d32f2f",
                fontweight="bold", zorder=5)

# ---- Knoten ----
for k in reihenfolge:
    x = knoten_x[k]
    circ = patches.Circle((x, y_leitung), 0.18,
                          facecolor="#1f5f8b", edgecolor="#0d3a5c",
                          lw=1.5, zorder=6)
    ax.add_patch(circ)
    ax.text(x, y_leitung, k, ha="center", va="center", color="white",
            fontsize=9, fontweight="bold", zorder=7)

# ---- Einspeiser und Last ----
for e in einheiten:
    x = knoten_x[e["knoten"]]
    anteil = e["wert"] / e["kap"] if e["kap"] > 0 else 0
    if e["typ"] == "gen":
        y_sym = y_leitung + 1.2
        size = 400 + 1500 * anteil
        ax.scatter(x, y_sym, s=size, c=e["farbe"], marker="^",
                   edgecolors="black", lw=1.2, zorder=5)
        ax.plot([x, x], [y_leitung, y_sym - 0.15],
                color="#1a1a1a", lw=1.5, zorder=1)
        ax.text(x, y_sym + 0.55, e["name"], ha="center", va="bottom",
                fontsize=10, fontweight="bold")
        if zeige_werte:
            ax.text(x, y_sym - 0.05, f"{e['wert']:.1f} GW",
                    ha="center", va="center", fontsize=9, color="white",
                    fontweight="bold", zorder=6)
    else:
        y_sym = y_leitung - 1.2
        groesse = 0.35 + 0.45 * anteil
        rect = patches.Rectangle((x - groesse / 2, y_sym - groesse / 2),
                                 groesse, groesse,
                                 facecolor=e["farbe"], edgecolor="#f57f17",
                                 lw=1.5, zorder=5)
        ax.add_patch(rect)
        ax.plot([x, x], [y_leitung, y_sym + groesse / 2],
                color="#1a1a1a", lw=1.5, zorder=1)
        ax.text(x, y_sym - 0.6, e["name"], ha="center", va="top",
                fontsize=10, fontweight="bold")
        if zeige_werte:
            ax.text(x, y_sym, f"{e['wert']:.1f} GW",
                    ha="center", va="center", fontsize=9, color="black",
                    fontweight="bold", zorder=6)

ax.set_xlim(0, 11)
ax.set_ylim(-0.8, 4.5)
ax.set_aspect("equal")
ax.axis("off")

# ---- Legende ----
legend_elements = [
    Line2D([0], [0], marker="^", color="w", markerfacecolor="#9c27b0",
           markeredgecolor="black", markersize=14, label="Wind"),
    Line2D([0], [0], marker="^", color="w", markerfacecolor="#43a047",
           markeredgecolor="black", markersize=14, label="Solar"),
    Line2D([0], [0], marker="^", color="w", markerfacecolor="#1565c0",
           markeredgecolor="black", markersize=14, label="Weitere EE"),
    Line2D([0], [0], marker="s", color="w", markerfacecolor="#fdd835",
           markeredgecolor="#f57f17", markersize=14, label="Last"),
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
    st.subheader("Aktuelle Leistung")
    erz_gesamt = gen_wind_gw + gen_solar_gw + gen_weitere_gw
    bilanz = erz_gesamt - last_gw

    st.metric("Wind",       f"{gen_wind_gw:.1f} GW",
              f"{wind_pct} % von {KAP_WIND_GW:.0f} GW")
    st.metric("Solar",      f"{gen_solar_gw:.1f} GW",
              f"{solar_pct} % von {KAP_SOLAR_GW:.0f} GW")
    st.metric("Weitere EE", f"{gen_weitere_gw:.1f} GW",
              f"{weitere_pct} % von {KAP_WEITERE_GW:.0f} GW")
    st.metric("Erzeugung gesamt", f"{erz_gesamt:.1f} GW")
    st.metric("Last", f"{last_gw:.1f} GW",
              f"{last_pct} % von {LAST_MAX_GW:.0f} GW")
    st.metric("Bilanz", f"{bilanz:+.1f} GW",
              delta="Ueberschuss" if bilanz > 0 else "Defizit",
              delta_color="normal" if bilanz > 0 else "inverse")

    st.markdown("---")
    st.subheader("Segmentfluesse")
    for i, f in enumerate(fluesse):
        a = reihenfolge[i]
        b = reihenfolge[i + 1]
        richtung = "->" if f > 0 else ("<-" if f < 0 else "--")
        st.write(f"{a} {richtung} {b}: **{f:+.1f} GW**")

st.caption(f"Installierte Leistung Deutschland (gerundet, Stand Anfang 2026): "
           f"Wind {KAP_WIND_GW:.0f} GW, Solar {KAP_SOLAR_GW:.0f} GW, "
           f"weitere EE {KAP_WEITERE_GW:.0f} GW (Wasser + Biomasse + sonst.). "
           f"Spitzenlast typ. {LAST_MAX_GW:.0f} GW. "
           f"Quelle: BNetzA Marktstammdatenregister / Fraunhofer ISE.")