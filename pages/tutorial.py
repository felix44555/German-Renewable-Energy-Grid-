import streamlit as st

st.set_page_config(page_title="Tutorial", layout="wide")

st.title("Tutorial: Allgemeines zum Simulator")
st.write("Willkommen im Tutorial! Bevor du in den Simulator startest, klären wir die wichtigsten Grundlagen.")

st.divider()

# 1. Was ist diese Website?
st.header("1. Was ist diese Website?")
st.write(
    "Diese Website ist ein interaktiver **Netzsimulator für Deutschland**. Sie nutzt reale Verbrauchs- und Erzeugungsdaten "
    "(von der SMARD-Plattform der Bundesnetzagentur) und verbindet sie mit einem vereinfachten Modell des deutschen "
    "Höchstspannungsnetzes. Du übernimmst die Rolle der Netzplanung und musst versuchen, dass das Stromnetz "
    "effektiv zu verändern, um den Anteil der erneuerbaren Energieen im Energiemix zu erhöhen."
)

# 2. Was ist das Übertragungsnetz?
st.header("2. Was ist ein Übertragungsnetz?")
st.write(
    "Das Stromnetz besteht aus dem Übertragungsnetz und dem Verteilnetz. Das Übertragungsnetz ist dabei der Teil, "
    "der große Mengen Energie über weite Strecken bei Höchstspannung (220 kV und 380 kV) transportiert. Auch Hochspannugns-"
    "Gleichstromübertragung (HGÜ) zählt zum Übertragungsnetz, jedoch wird diese in dieser Simulation nicht seperat betrachtet. "
    "Das Übertragungsnetz wird benötigt, da der Energiebedarf nicht immer an einem ort selber gedeckt werden kann."
)

# 3. Herausforderungen des Netzes
st.header("3. Welche Herausforderungen gibt es aktuell?")
with st.container():
    st.markdown("""
    Die Energiewende stellt das Netz vor große Herausforderungen:
    * **Geografische Ungleichverteilung:** Die meiste Windenergie wird im Norden generiert, der großteil der Industrie (und der höchste Energiebedarf) befindet sich jedoch im Süden. Zudem befindet sich die meißte solare Energiegewinnung im Süden des Landes, und muss in Zeiten mit wenig Wind in den Norden transportiert werden.
    * **Wetterabhängigkeit:** Wind und Sonne liefern nicht konstant Strom. Da oft nur einer der Erzeuger gleichzeitig ausfällt, besteht an solchen Tagen hoher transport bedarf.".
    * **Netzengpässe (Bottlenecks):** Wenn zu viel Windstrom vom Norden in den Süden drängt, reichen die Kapazitäten des Übertragungsnetz oft nicht aus. In solchen fällen muss die Erzeugung abgeregelt werden und im Süden muss Energie auf andere, oft fossile Art gewonnen werden.
    """)

# 4. Ziel der Simulation (KPIs)
st.header("4. Was ist das Ziel dieser Simulation?")
st.info(
    "Deine Aufgabe ist es, eine sogenannte **KPI (Key Performance Indicator)** zu optimieren. Das Netz ist am besten, wenn folgende Ziele erreicht werden:"
)
c1, c2, c3 = st.columns(3)

with c1:
    st.subheader(" Leitungen schützen")
    st.write("Keine Leitung darf über 100% ausgelastet sein, sonst drohen Stromausfälle.")
with c2:
    st.subheader(" Abregelung minimieren")
    st.write("Verhindere, dass sauberer Wind- und Solarstrom weggeworfen (abgeregelt) werden muss, weil das Netz voll ist.")
with c3:
    st.subheader(" Nicht unnötig viel Ausbau")
    st.write("Versuche dein Netz so effizient wie möglich zu bauen. Wenn du zu viel Kapazitäten hinzufügst, die garnicht genutzt werden, sinkt die Effizienz.")

# 5. Wie funktioniert die Lastflussrechnung?
st.header("5. Wie funktioniert die Lastflussrechnung?")

with st.expander("Didaktisch vereinfachte Herleitung des DC-Lastflusses", expanded=False):
    st.info(
        "**Motivation:** Die Berechnung des DC-Lastflusses ist eine etablierte Methode zur schnellen, linearen "
        "Näherung von Leistungsflüssen in Hochspannungsnetzen. Anstatt zunächst die komplexen AC-Leistungsgleichungen "
        "mit all ihren trigonometrischen Summen aufzustellen, können die bekannten Näherungen didaktisch sinnvoll direkt "
        "zu Beginn an den fundamentalen physikalischen Größen angesetzt werden."
    )

    st.markdown("### Grundlegende Annahmen")
    st.markdown("Folgende praxisnahe Annahmen für Hochspannungsnetze bilden die Grundlage:")
    st.markdown("* Die Spannungsbeträge an allen Knoten sind nahezu identisch und liegen nahe am Nennwert:")
    st.latex(r"|V| \approx 1 \text{ p.u.}")
    
    st.markdown("* Die Winkeldifferenzen zwischen benachbarten Knoten sind klein (erwartet unter 30°).")
    st.markdown("* Der ohmsche Widerstand R der Leitungen ist sehr viel kleiner als die Leitungsreaktanz X, weshalb er vernachlässigt wird:")
    st.latex(r"X \gg R")

    st.divider()

    st.markdown("### Schritt 1: Näherung der Knotenspannungen")
    st.markdown("Die komplexe Spannung an einem Knoten i lautet in der Exponentialform:")
    st.latex(r"V_i = |V_i|e^{j\theta_i}")
    
    st.markdown("Wir setzen nun den konstanten Spannungsbetrag (|V| ≈ 1) und die Taylor-Näherung für kleine Winkel ein. Damit vereinfacht sich die Knotenspannung drastisch zu:")
    st.latex(r"V_i \approx 1 + j\theta_i")

    st.markdown("### Schritt 2: Näherung der Netzadmittanzen")
    st.markdown("Die Admittanz Y berechnet sich allgemein als Umkehrwert der Impedanz. Da der Wirkwiderstand R vernachlässigt wird, besteht die Leitung zwischen den Knoten i und k rein aus der Suszeptanz B. Für die Admittanz gilt somit:")
    st.latex(r"Y_{ik} \approx -jB_{ik}")

    st.markdown("### Schritt 3: Berechnung des Zweigstroms (Ohmsches Gesetz)")
    st.markdown("Der Strom I, der vom Knoten i zum Knoten k fließt, ergibt sich direkt aus der Spannungsdifferenz multipliziert mit der Admittanz:")
    st.latex(r"I_{ik} = Y_{ik}(V_i - V_k)")
    
    st.markdown("Setzen wir nun unsere sehr simplen Näherungen aus Schritt 1 und 2 ein:")
    st.latex(r"I_{ik} = -jB_{ik} \big( (1 + j\theta_i) - (1 + j\theta_k) \big)")
    
    st.markdown("Die reellen Einsen heben sich durch die Subtraktion auf:")
    st.latex(r"I_{ik} = -jB_{ik}(j\theta_i - j\theta_k)")
    
    st.markdown("Klammert man das j aus, ergibt sich durch die Multiplikation $-j \cdot j = 1$. Wir erhalten einen rein reellen Ausdruck für den Strom:")
    st.latex(r"I_{ik} = B_{ik}(\theta_i - \theta_k)")

    st.markdown("### Schritt 4: Berechnung der Wirkleistung")
    st.markdown("Die komplexe Scheinleistung S, die in den Zweig fließt, ist das Produkt aus der Knotenspannung und dem konjugiert komplexen Strom:")
    st.latex(r"S_{ik} = V_i I_{ik}^*")
    
    st.markdown("Da unser genäherter Strom aus Schritt 3 rein reell ist, gilt $I_{ik}^* = I_{ik}$. Setzen wir die Gleichungen ein:")
    st.latex(r"S_{ik} \approx (1 + j\theta_i) \cdot B_{ik}(\theta_i - \theta_k)")
    
    st.markdown("Ausmultipliziert ergibt das:")
    st.latex(r"S_{ik} = B_{ik}(\theta_i - \theta_k) + j\theta_i B_{ik}(\theta_i - \theta_k)")
    
    st.markdown("Beim DC-Lastfluss interessiert uns definitionsgemäß ausschließlich die Wirkleistung P (der Realteil der Scheinleistung). Wir ignorieren den Imaginärteil und erhalten sofort die finale, lineare Bestimmungsgleichung für den Leistungsfluss über den Leitungszweig:")
    st.latex(r"P_{ik} = B_{ik}(\theta_i - \theta_k)")

    st.success("**Zusammenfassung:** Anstatt am Ende einer langen Herleitung Annahmen auf unhandliche Sinus- und Kosinus-Funktionen anzuwenden, zeigt dieser Ansatz direkt am Ohmschen Gesetz, wie sich das Wechselstromnetz durch die DC-Näherungen mathematisch quasi in ein lineares Gleichstromnetz verwandelt. Die Summe aller abfließenden Zweigleistungen P an einem Knoten führt dann nahtlos zur bekannten Gleichung für die Einspeiseleistung P am Knoten i:")
    
    st.latex(r"P_i = \sum_{k=1}^N B_{ik}(\theta_i - \theta_k)")


st.divider()

# --- Return Button ---
st.success("Grundlagen verstanden? Dann bist du bereit für den Sandbox-Modus!")
st.page_link("app.py", label="Zurück zum Simulator", icon="🎮")