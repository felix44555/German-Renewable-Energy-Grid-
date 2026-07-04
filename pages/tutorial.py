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
    st.write("Keine Leitung darf über 100 % ausgelastet sein, sonst drohen Stromausfälle.")
with c2:
    st.subheader(" Abregelung minimieren")
    st.write("Verhindere, dass sauberer Wind- und Solarstrom weggeworfen (abgeregelt) werden muss, weil das Netz voll ist.")
with c3:
    st.subheader(" Nicht unnötig viel Ausbau")
    st.write("Versuche dein Netz so effizient wie möglich zu bauen. Wenn du zu viel Kapazitäten hinzufügst, die garnicht genutzt werden, sinkt die Effizienz deines Netztes.")

# 5. Wie funktioniert die Lastflussrechnung?
st.header("5. Wie funktioniert die Lastflussrechnung?")

st.markdown("### DC-Lastflussmodell")

st.markdown("Im DC-Lastfluss gelten die vereinfachenden Annahmen:")

st.markdown("**1. Spannungsbeträge sind näherungsweise konstant:**")
st.latex(r"|V| \approx 1")

st.markdown("**2. Leitungswiderstände werden vernachlässigt:**")
st.latex(r"R \ll X")

st.markdown("**3. Winkeldifferenzen sind klein:**")
st.latex(r"\sin(\theta_a - \theta_b) \approx \theta_a - \theta_b")

st.markdown("**4. Es wird nur Wirkleistung betrachtet.**")

st.divider()

st.markdown("Für eine Leitung zwischen zwei Knoten $a$ und $b$ gilt:")

st.latex(r"P_{ab} = b_{ab}(\theta_a - \theta_b)")

st.markdown("mit")

st.latex(r"b_{ab} = \frac{1}{x_{ab}}")

st.markdown("Damit ergibt sich äquivalent:")

st.latex(r"P_{ab} = \frac{\theta_a - \theta_b}{x_{ab}}")

st.divider()

st.markdown("Die Knotengleichung für einen Knoten $m$ lautet allgemein:")

st.latex(r"P_m = \sum_{n \in N(m)} b_{mn}(\theta_m - \theta_n)")

st.markdown(
    "Dabei ist $N(m)$ die Menge der Nachbarknoten von $m$."
)



st.divider()

# --- Return Button ---
st.success("Grundlagen verstanden? Dann bist du bereit für den Sandbox-Modus!")
st.page_link("app.py", label="Zurück zum Simulator", icon="🎮")