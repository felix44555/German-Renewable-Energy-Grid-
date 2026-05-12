# -*- coding: utf-8 -*-
"""
Streamlit App: Vereinfachte Stromkarte Deutschland
5 Zonen, animierter Tagesverlauf mit erneuerbaren Energien
"""

import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import time

# ============================================================
# Konfiguration
# ============================================================
st.set_page_config(page_title="DE Stromkarte", layout="wide")
st.title("Vereinfachte Stromkarte Deutschland")
st.write("Erneuerbare Energien im Tagesverlauf - 5 Zonen.")

# ============================================================
# Zonen-Definition (vereinfacht als Rechtecke auf einer DE-Karte)
# Position (x, y) und Größe (breite, hoehe) auf einer Karte
# Karte ungefähr: x: 0-10, y: 0-12 (Norden oben)
# ============================================================
zonen = {
    "Nord": {
        "pos": (3.5, 9.0), "size": (4.0, 2.5),
        "wind_max": 1.0,    # hoher Windanteil (Offshore + Onshore)
        "solar_max": 0.5,   # weniger Solar
        "bio_max": 0.4,
        "color_box": "#e3f2fd"
    },
    "West": {
        "pos": (1.5, 5.5), "size": (3.0, 3.5),
        "wind_max": 0.5,
        "solar_max": 0.7,
        "bio_max": 0.5,
        "color_box": "#e8f5e9"
    },
    "Mitte": {
        "pos": (4.5, 5.5), "size": (3.0, 3.5),
        "wind_max": 0.6,
        "solar_max": 0.7,
        "bio_max": 0.6,
        "color_box": "#fff9c4"
    },
    "Ost": {
        "pos": (7.5, 5.5), "size": (3.0, 3.5),
        "wind_max": 0.8,
        "solar_max": 0.7,
        "bio_max": 0.7,
        "color_box": "#fce4ec"
    },
    "Süd": {
        "pos": (3.0, 1.5), "size": (5.5, 4.0),
        "wind_max": 0.3,
        "solar_max": 1.0,   # viel Solar
        "bio_max": 0.6,
        "color_box": "#ffe0b2"
    },
}

# ============================================================
# Tagesverlauf-Modelle (24 Stunden)
# ============================================================
def solar_profil(stunde):
    # Solar: Glockenkurve, Maximum mittags
    if 6 <= stunde <= 20:
        return max(0, np.sin((stunde - 6) / 14 * np.pi))
    return 0

def wind_profil(stunde):
    # Wind: nachts und morgens etwas stärker, leicht schwankend
    return 0.5 + 0.3 * np.sin((stunde - 3) / 24 * 2 * np.pi) + 0.1 * np.sin(stunde / 6 * np.pi)

def bio_profil(stunde):
    # Biomasse: nahezu konstant (Grundlast)
    return 0.7

def last_profil(stunde):
    # Verbrauch: Morgenpeak ~8h, Mittagsdelle, Abendpeak ~19h
    morgen = np.exp(-((stunde - 8) ** 2) / 8)
    abend = np.exp(-((stunde - 19) ** 2) / 6)
    grundlast = 0.55
    return grundlast + 0.3 * morgen + 0.4 * abend

def tageszeit_label(stunde):
    if 5 <= stunde < 11:
        return "Morgen"
    elif 11 <= stunde < 16:
        return "Mittag"
    elif 16 <= stunde < 21:
        return "Abend"
    else:
        return "Nacht"

# ============================================================
# Steuerung
# ============================================================
col_ctrl1, col_ctrl2, col_ctrl3 = st.columns([1, 1, 2])

with col_ctrl1:
    auto_play = st.checkbox("Animation starten", value=False)
with col_ctrl2:
    speed = st.select_slider("Geschwindigkeit", 
                              options=["langsam", "mittel", "schnell"], 
                              value="mittel")
with col_ctrl3:
    manual_h = st.slider("Uhrzeit (Stunde)", 0, 23, 12, 1)

speed_map = {"langsam": 0.6, "mittel": 0.25, "schnell": 0.08}
delay = speed_map[speed]

# Platzhalter für Animation
karte_platz = st.empty()
info_platz = st.empty()
plot_platz = st.empty()

# ============================================================
# Zeichenfunktion
# ============================================================
def zeichne_karte(stunde):
    fig, (ax_karte, ax_zeit) = plt.subplots(1, 2, figsize=(14, 7),
                                             gridspec_kw={"width_ratios": [2, 1]})
    
    # ----- KARTE -----
    # Grober DE-Umriss als Hintergrund
    de_outline = patches.FancyBboxPatch((0.5, 0.5), 10, 11.5,
                                         boxstyle="round,pad=0.1",
                                         facecolor="#f5f5f5", 
                                         edgecolor="gray", lw=1.5)
    ax_karte.add_patch(de_outline)
    
    # Erzeugungsanteile dieser Stunde
    s_p = solar_profil(stunde)
    w_p = wind_profil(stunde)
    b_p = bio_profil(stunde)
    
    gesamt_solar = 0
    gesamt_wind = 0
    gesamt_bio = 0
    
    for name, z in zonen.items():
        x, y = z["pos"]
        w, h = z["size"]
        
        # Erzeugung in dieser Zone
        solar_z = s_p * z["solar_max"]
        wind_z = w_p * z["wind_max"]
        bio_z = b_p * z["bio_max"]
        gesamt = solar_z + wind_z + bio_z
        
        gesamt_solar += solar_z
        gesamt_wind += wind_z
        gesamt_bio += bio_z
        
        # Box für Zone
        rect = patches.Rectangle((x, y), w, h, 
                                  facecolor=z["color_box"],
                                  edgecolor="black", lw=1.2, alpha=0.7)
        ax_karte.add_patch(rect)
        
        # Zonenname
        ax_karte.text(x + w/2, y + h - 0.3, name,
                      ha="center", va="top", fontsize=13, fontweight="bold")
        
        # Symbole für Erzeugungsarten (Größe abhängig von Erzeugung)
        cx, cy = x + w/2, y + h/2
        
        # Solar (gelb, links) - Größe ~ solar_z
        if solar_z > 0.05:
            sun_size = 200 + solar_z * 800
            ax_karte.scatter(cx - 0.8, cy - 0.2, s=sun_size, c="gold", 
                            marker="o", edgecolors="orange", lw=1.5, zorder=5)
            ax_karte.text(cx - 0.8, cy - 0.2, "S", ha="center", va="center",
                         fontsize=9, fontweight="bold", zorder=6)
        
        # Wind (blau, mittig) - Größe ~ wind_z
        if wind_z > 0.05:
            wind_size = 200 + wind_z * 800
            ax_karte.scatter(cx, cy - 0.2, s=wind_size, c="lightblue", 
                            marker="^", edgecolors="steelblue", lw=1.5, zorder=5)
            ax_karte.text(cx, cy - 0.2, "W", ha="center", va="center",
                         fontsize=9, fontweight="bold", zorder=6)
        
        # Biomasse (grün, rechts)
        if bio_z > 0.05:
            bio_size = 200 + bio_z * 600
            ax_karte.scatter(cx + 0.8, cy - 0.2, s=bio_size, c="lightgreen",
                            marker="s", edgecolors="green", lw=1.5, zorder=5)
            ax_karte.text(cx + 0.8, cy - 0.2, "B", ha="center", va="center",
                         fontsize=9, fontweight="bold", zorder=6)
        
        # Gesamterzeugung als Text
        ax_karte.text(x + w/2, y + 0.2, f"Σ {gesamt:.2f}",
                      ha="center", va="bottom", fontsize=10, 
                      style="italic", color="darkblue")
    
    ax_karte.set_xlim(-0.5, 11.5)
    ax_karte.set_ylim(-0.5, 12.5)
    ax_karte.set_aspect("equal")
    ax_karte.axis("off")
    
    tz = tageszeit_label(stunde)
    ax_karte.set_title(f"{stunde:02d}:00 Uhr - {tz}", fontsize=15, fontweight="bold")
    
    # Legende
    legend_elements = [
        plt.scatter([], [], s=300, c="gold", marker="o", 
                   edgecolors="orange", label="Solar (S)"),
        plt.scatter([], [], s=300, c="lightblue", marker="^",
                   edgecolors="steelblue", label="Wind (W)"),
        plt.scatter([], [], s=300, c="lightgreen", marker="s",
                   edgecolors="green", label="Biomasse (B)"),
    ]
    ax_karte.legend(handles=legend_elements, loc="lower left", fontsize=10)
    
    # ----- TAGESVERLAUF rechts -----
    stunden = np.arange(0, 24, 0.25)
    solar_v = [solar_profil(h) * sum(z["solar_max"] for z in zonen.values()) for h in stunden]
    wind_v = [wind_profil(h) * sum(z["wind_max"] for z in zonen.values()) for h in stunden]
    bio_v = [bio_profil(h) * sum(z["bio_max"] for z in zonen.values()) for h in stunden]
    last_v = [last_profil(h) * 4.0 for h in stunden]  # skalierte Last
    
    ax_zeit.fill_between(stunden, 0, bio_v, color="lightgreen", 
                         label="Biomasse", alpha=0.8)
    ax_zeit.fill_between(stunden, bio_v, np.array(bio_v) + np.array(wind_v), 
                         color="lightblue", label="Wind", alpha=0.8)
    ax_zeit.fill_between(stunden, np.array(bio_v) + np.array(wind_v),
                         np.array(bio_v) + np.array(wind_v) + np.array(solar_v),
                         color="gold", label="Solar", alpha=0.8)
    ax_zeit.plot(stunden, last_v, "r-", lw=2.5, label="Verbrauch (Last)")
    
    # Aktuelle Zeit markieren
    ax_zeit.axvline(stunde, color="black", lw=2, linestyle="--", alpha=0.7)
    
    ax_zeit.set_xlim(0, 24)
    ax_zeit.set_xticks(range(0, 25, 4))
    ax_zeit.set_xlabel("Uhrzeit")
    ax_zeit.set_ylabel("Leistung (relative Einheiten)")
    ax_zeit.set_title("Tagesverlauf Deutschland gesamt")
    ax_zeit.legend(loc="upper left", fontsize=9)
    ax_zeit.grid(True, alpha=0.3)
    
    plt.tight_layout()
    return fig, gesamt_solar, gesamt_wind, gesamt_bio

# ============================================================
# Anzeige (Animation oder statisch)
# ============================================================
def update_anzeige(stunde):
    fig, gs, gw, gb = zeichne_karte(stunde)
    karte_platz.pyplot(fig)
    plt.close(fig)
    
    last = last_profil(stunde) * 4.0
    erzeugung = gs + gw + gb
    bilanz = erzeugung - last
    
    with info_platz.container():
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Solar", f"{gs:.2f}")
        c2.metric("Wind", f"{gw:.2f}")
        c3.metric("Biomasse", f"{gb:.2f}")
        c4.metric("Verbrauch", f"{last:.2f}")
        c5.metric("Bilanz EE", f"{bilanz:+.2f}",
                  delta="Überschuss" if bilanz > 0 else "Defizit")

if auto_play:
    # Animation läuft endlos bis Checkbox deaktiviert
    for _ in range(3):  # 3 Tagesdurchläufe, dann stoppen
        for h in range(24):
            update_anzeige(h)
            time.sleep(delay)
        if not auto_play:
            break
    st.info("Animation beendet. Häkchen erneut setzen zum Neustart oder Slider verwenden.")
else:
    update_anzeige(manual_h)
    st.caption("Tipp: Animation aktivieren oder Slider bewegen.")