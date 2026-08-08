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
    "Deine Aufgabe ist es, den **Grid Performance Score** zu optimieren. "
    "Er bewertet, wie gut dein Stromnetz erneuerbare Energien nutzt, "
    "Leitungsüberlastungen vermeidet und den zusätzlichen Ausbau begrenzt."
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

st.markdown(
    "Für die vereinfachte Berechnung des Leistungsflusses im Netz verwenden wir "
    "ein DC-Lastflussmodell. Dabei gelten folgende vereinfachende Annahmen:"
)

st.markdown("**1. Spannungsbeträge sind näherungsweise konstant:**")
st.latex(r"|V| \approx 1\,pu")

st.markdown("**2. Leitungswiderstände werden gegenüber der Reaktanz vernachlässigt:**")
st.latex(r"R \ll X")

st.markdown("**3. Die Winkeldifferenzen zwischen den Knoten sind klein:**")
st.latex(r"\sin(\theta_a-\theta_b)\approx\theta_a-\theta_b")

st.markdown("**4. Es wird nur Wirkleistung betrachtet.**")

st.divider()

st.markdown("### Leistungsfluss zwischen zwei Knoten")

st.markdown(
    "Unter diesen Annahmen kann der Wirkleistungsfluss auf einer Leitung "
    "zwischen den Knoten $a$ und $b$ näherungsweise berechnet werden als:"
)

st.latex(
    r"P_{ab}\approx\frac{\theta_a-\theta_b}{x_{ab}}"
)


st.markdown(
    "Dabei sind $\\theta_a$ und $\\theta_b$ die Spannungswinkel der beiden Knoten "
    "und $x_{ab}$ die Leitungsreaktanz in Per Unit."
)

st.markdown("Alternativ kann man mit dem Leitwertfaktor schreiben:")

st.latex(r"b_{ab}=\frac{1}{x_{ab}}")

st.latex(r"P_{ab}=b_{ab}(\theta_a-\theta_b)")

st.divider()

st.markdown("### Knotengleichung")

st.markdown(
    "Für einen Knoten $m$ ergibt sich der gesamte Leistungsfluss aus der Summe "
    "der Leistungsflüsse zu allen angeschlossenen Nachbarknoten:"
)

st.latex(
    r"P_m=\sum_{n\in N(m)}\frac{\theta_m-\theta_n}{x_{mn}}"
)

st.markdown(
    "Dabei bezeichnet $N(m)$ die Menge der Nachbarknoten von $m$. "
    "Die Gleichungen aller Knoten können anschließend als lineares "
    "Gleichungssystem in Matrixform geschrieben werden."
)

st.divider()

with st.expander("Beispielrechnung: DC-Lastfluss mit 3 Knoten", expanded=False):

    st.markdown("### 1. Eingaben")

    st.markdown(
        "Wir betrachten ein vereinfachtes Netz mit drei Knoten $i$, $j$ und $k$. "
        "Die Knoten $i$ und $j$ speisen Leistung ein, während Knoten $k$ "
        "Leistung aufnimmt."
    )

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.image(
            "pages/dc_3_knoten.jpeg",
            caption="Dreiknoten-Netz für die Beispielrechnung",
            use_container_width=True
        )

    st.markdown("Für die Per-Unit-Rechnung werden zunächst die Basisgrößen festgelegt:")

    st.latex(r"V_B=380\,\mathrm{kV}")

    st.latex(r"S_B=1000\,\mathrm{MVA}")

    st.markdown("Daraus ergibt sich die Basisimpedanz:")

    st.latex(
        r"Z_B=\frac{V_B^2}{S_B}"
        r"=\frac{380^2}{1000}"
        r"=144{,}4\,\Omega"
    )

    st.markdown("Die eingespeisten bzw. entnommenen Leistungen sind:")

    st.latex(r"P_i=500\,\mathrm{MW}")

    st.latex(r"P_j=300\,\mathrm{MW}")

    st.latex(r"P_k=-800\,\mathrm{MW}")

    st.markdown("Das Netz ist ausgeglichen, weil gilt:")

    st.latex(
        r"P_i+P_j+P_k=500+300-800=0\,\mathrm{MW}"
    )

    st.markdown("Für die Lastflussrechnung werden die Leistungen in Per Unit umgerechnet:")

    st.latex(
        r"P_{i,pu}=\frac{500}{1000}=0{,}5\,pu"
    )

    st.latex(
        r"P_{j,pu}=\frac{300}{1000}=0{,}3\,pu"
    )

    st.latex(
        r"P_{k,pu}=\frac{-800}{1000}=-0{,}8\,pu"
    )

    st.markdown("Die Leitungsreaktanzen betragen:")

    st.latex(r"X_{ij}=28{,}88\,\Omega")

    st.latex(r"X_{ik}=36{,}10\,\Omega")

    st.latex(r"X_{jk}=28{,}88\,\Omega")

    st.markdown(
        "Diese werden mit der Basisimpedanz in Per Unit umgerechnet:"
    )

    st.latex(
        r"x_{ij}=\frac{X_{ij}}{Z_B}"
        r"=\frac{28{,}88}{144{,}4}"
        r"=0{,}20\,pu"
    )

    st.latex(
        r"x_{ik}=\frac{X_{ik}}{Z_B}"
        r"=\frac{36{,}10}{144{,}4}"
        r"=0{,}25\,pu"
    )

    st.latex(
        r"x_{jk}=\frac{X_{jk}}{Z_B}"
        r"=\frac{28{,}88}{144{,}4}"
        r"=0{,}20\,pu"
    )

    st.divider()

    st.markdown("### 2. Reduzierte Gleichung")

    st.markdown(
        "Damit die Winkel eindeutig bestimmt werden können, wird ein Knoten "
        "als Referenzknoten gewählt. Hier setzen wir:"
    )

    st.latex(r"\theta_k=0")

    st.markdown(
        "Die Knotengleichungen für die verbleibenden unbekannten Winkel "
        "$\\theta_i$ und $\\theta_j$ ergeben:"
    )

    st.latex(
        r"""
        \begin{bmatrix}
        9 & -5\\
        -5 & 10
        \end{bmatrix}
        \begin{bmatrix}
        \theta_i\\
        \theta_j
        \end{bmatrix}
        =
        \begin{bmatrix}
        0{,}5\\
        0{,}3
        \end{bmatrix}
        """
    )

    st.markdown(
        "Die rechte Seite enthält dabei die eingespeiste bzw. entnommene "
        "Leistung in Per Unit."
    )

    st.markdown("Durch Lösen des linearen Gleichungssystems erhält man:")

    st.latex(
        r"\theta_i=0{,}10\,\mathrm{rad}=5{,}73^\circ"
    )

    st.latex(
        r"\theta_j=0{,}08\,\mathrm{rad}=4{,}58^\circ"
    )

    st.latex(r"\theta_k=0")

    st.divider()

    st.markdown("### 3. Ergebnisse")

    st.markdown(
        "Die Leistungsflüsse auf den Leitungen werden zunächst in Per Unit "
        "berechnet und anschließend in MW umgerechnet."
    )

    st.markdown("**Leitung von i nach j:**")

    st.latex(
        r"P_{ij}"
        r"=\frac{\theta_i-\theta_j}{x_{ij}}"
        r"=\frac{0{,}10-0{,}08}{0{,}20}"
        r"=0{,}10\,pu"
        r"=100\,\mathrm{MW}"
    )

    st.markdown("**Leitung von i nach k:**")

    st.latex(
        r"P_{ik}"
        r"=\frac{\theta_i-\theta_k}{x_{ik}}"
        r"=\frac{0{,}10-0}{0{,}25}"
        r"=0{,}40\,pu"
        r"=400\,\mathrm{MW}"
    )

    st.markdown("**Leitung von j nach k:**")

    st.latex(
        r"P_{jk}"
        r"=\frac{\theta_j-\theta_k}{x_{jk}}"
        r"=\frac{0{,}08-0}{0{,}20}"
        r"=0{,}40\,pu"
        r"=400\,\mathrm{MW}"
    )

    st.markdown(
        "Damit fließen insgesamt 800 MW zu Knoten $k$. "
        "Zusätzlich fließen 100 MW von Knoten $i$ nach Knoten $j$."
    )

    st.success(
        "Interpretation: Der Haupttransport erfolgt von den einspeisenden "
        "Knoten i und j zum Verbrauchsknoten k. Zusätzlich fließen 100 MW "
        "von i nach j, da die Knotenspannungswinkel unterschiedlich sind."
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