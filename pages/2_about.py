import streamlit as st

st.set_page_config(page_title="About", layout="wide")

st.title("About: Allgemeines zum Simulator")
st.write("Auf dieser Seite findest du Hintergrundinformationen zum Stromnetzmodell,zu den verwendeten Daten und zur DC-Lastflussberechnung.")

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

with st.expander("Beispielrechnung: DC-Lastfluss mit 3 Knoten", expanded=False):

    st.markdown("### 1. Eingaben")

    st.markdown(
        "Wir betrachten ein kleines Netz mit drei Knoten $i$, $j$ und $k$. "
        "Die Knoten $i$ und $j$ speisen jeweils Leistung ein, während Knoten $k$ Leistung aufnimmt."
    )

    st.image(
    "pages/dc_3_knoten.jpeg",
    caption="Dreiknoten-Netz für die Beispielrechnung",
    use_container_width=True
    )

    st.latex(r"P_i = +4 \ \mathrm{MW}")
    st.latex(r"P_j = +4 \ \mathrm{MW}")
    st.latex(r"P_k = -8 \ \mathrm{MW}")

    st.markdown("Das Netz ist ausgeglichen, weil gilt:")

    st.latex(r"P_i + P_j + P_k = 4 + 4 - 8 = 0")

    st.markdown("Die Leitungsreaktanzen sind:")

    st.latex(r"x_{ij} = 8")
    st.latex(r"x_{ik} = 14")
    st.latex(r"x_{jk} = 10")

    st.markdown("Daraus ergeben sich die Leitwertfaktoren:")

    st.latex(r"b_{ij} = \frac{1}{8}")
    st.latex(r"b_{ik} = \frac{1}{14}")
    st.latex(r"b_{jk} = \frac{1}{10}")

    st.divider()

    st.markdown("### 2. Reduzierte Gleichung")

    st.markdown(
        "Damit die Winkel eindeutig berechnet werden können, wird ein Knoten als Referenzknoten gewählt. "
        "Hier setzen wir:"
    )

    st.latex(r"\theta_k = 0")

    st.markdown("Die DC-Lastflussgleichung wird in Matrixform geschrieben als:")

    st.latex(r"P = B' \theta")

    st.markdown("Da Knoten $k$ der Referenzknoten ist, bleiben nur die Winkel $\\theta_i$ und $\\theta_j$ als Unbekannte übrig.")

    st.latex(
        r"""
        \begin{bmatrix}
        \frac{11}{56} & -\frac{1}{8} \\
        -\frac{1}{8} & \frac{9}{40}
        \end{bmatrix}
        \begin{bmatrix}
        \theta_i \\
        \theta_j
        \end{bmatrix}
        =
        \begin{bmatrix}
        4 \\
        4
        \end{bmatrix}
        """
    )

    st.markdown("Durch Lösen dieses linearen Gleichungssystems erhält man:")

    st.latex(r"\theta_i = 49")
    st.latex(r"\theta_j = 45")
    st.latex(r"\theta_k = 0")

    st.divider()

    st.markdown("### 3. Ergebnisse")

    st.markdown("Die Leistungsflüsse auf den Leitungen ergeben sich aus:")

    st.latex(r"P_{ab} = \frac{\theta_a - \theta_b}{x_{ab}}")

    st.markdown("**Leitung von i nach k:**")

    st.latex(r"P_{ik} = \frac{\theta_i - \theta_k}{x_{ik}} = \frac{49 - 0}{14} = 3{,}5 \ \mathrm{MW}")

    st.markdown("**Leitung von j nach k:**")

    st.latex(r"P_{jk} = \frac{\theta_j - \theta_k}{x_{jk}} = \frac{45 - 0}{10} = 4{,}5 \ \mathrm{MW}")

    st.markdown("**Leitung von i nach j:**")

    st.latex(r"P_{ij} = \frac{\theta_i - \theta_j}{x_{ij}} = \frac{49 - 45}{8} = 0{,}5 \ \mathrm{MW}")

    st.markdown("Damit ergibt sich die Knotenkontrolle:")

    st.latex(r"\text{Knoten } i: \quad P_{ik} + P_{ij} = 3{,}5 + 0{,}5 = 4 \ \mathrm{MW}")

    st.latex(r"\text{Knoten } j: \quad P_{jk} - P_{ij} = 4{,}5 - 0{,}5 = 4 \ \mathrm{MW}")

    st.latex(r"\text{Knoten } k: \quad P_{ik} + P_{jk} = 3{,}5 + 4{,}5 = 8 \ \mathrm{MW}")

    st.success(
        "Interpretation: Der Haupttransport erfolgt zu Knoten k. Zusätzlich fließt ein kleiner Ausgleichsstrom "
        "von Knoten i nach Knoten j."
    )



st.divider()

st.divider()

st.success(
    "Du kennst jetzt die wichtigsten Grundlagen des verwendeten Netzmodells."
)

col1, col2 = st.columns(2)

with col1:
    st.page_link(
        "pages/1_Tutorial.py",
        label="Zum interaktiven Tutorial",
        icon="📘",
    )

with col2:
    st.page_link(
        "app.py",
        label="Direkt zum Simulator",
        icon="🎮",
    )