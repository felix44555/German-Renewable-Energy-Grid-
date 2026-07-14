import streamlit as st
import pandas as pd
from visualization import build_line_utilization_chart, build_line_utilization_chart_24h, build_map, build_stack #build_balance_chart,

st.set_page_config(
    page_title="Tutorial",
    page_icon="📘",
    layout="wide",
)



# ============================================================
# Kopfbereich
# ============================================================

st.title("📘 Tutorial: Das deutsche Stromnetz gestalten")

st.write(
    "In diesem Tutorial lernst du Schritt für Schritt, wie du den Simulator "
    "bedienst, Netzengpässe erkennst und den Anteil erneuerbarer Energien erhöhst."
)

st.info(
    "Das Ziel ist nicht, einfach alle Slider auf den höchsten Wert zu stellen. "
    "Gesucht wird eine technisch sinnvolle Lösung mit hohem EE-Anteil, "
    "sicheren Leitungen und möglichst begrenztem Ausbau."
)


navigation_col1, navigation_col2 = st.columns(2)

with navigation_col1:
    st.page_link(
        "app.py",
        label="Simulator öffnen",
        icon="🎮",
    )

with navigation_col2:
    st.page_link(
        "pages/2_About.py",
        label="Modellgrundlagen",
        icon="📖",
    )




# ============================================================
# Tutorial-Ablauf
# ============================================================

st.header("Schritt 1: Szenario und Daten auswählen")

st.markdown(
    """
    Öffne den Simulator und betrachte zunächst die Seitenleiste.

    1. Wähle unter **Aufgabe** ein Szenario oder den Sandboxmodus aus.
    2. Klicke auf **Szenario-Startwerte laden**.
    3. Wenn du in der Sandbox Aufgabe bist, wähle ein Datum, für das du SMARD Daten möchtest. In den Szenarios ist das Datum vorgegeben.
    """
)

with st.expander("Was bedeuten diese Einstellungen?", expanded=True):
    st.markdown(
        """
        **Aufgabe**

        Bestimmt die Ausgangssituation und die Bedingungen, die für eine
        erfolgreiche Lösung erfüllt werden müssen. Hier kannst du auch in den Sandboxmodus wechseln.

        **Szenario-Startwerte laden**

        Setzt alle Stellgrößen auf die zum Szenario gehörenden Ausgangswerte zurück.


        **SMARD-Datum**

        Bestimmt, welcher Tag simuliert wird. Wind, Sonne und Stromverbrauch
        können sich von Tag zu Tag stark unterscheiden.
        """
    )



# ============================================================

st.header("Schritt 2: Den Ausgangszustand untersuchen")

st.markdown(
    """
    Verändere zunächst noch keinen Slider. Betrachte die fünf Kennzahlen im
    Bereich **24h Grid Performance Score**.
    """
)

metric_col1, metric_col2 = st.columns(2)

with metric_col1:
    st.markdown(
        """
        ### Grid Performance Score

        
        Ist eine errechnete Gesamtbewertung deiner Lösung.

        Ein hoher Wert bedeutet grundsätzlich:

        - hoher Anteil erneuerbarer Energien,
        - keine Netzüberlastung,
        - wenig Abschaltung von erneuerbaren Erzeugern. (also kein unnötig großer Ausbau)
        """
    )

    st.markdown(
        """
        ### 24h EE-Anteil [%]

        Zeigt, welcher Anteil des Tagesverbrauchs durch Wind, PV und nutzbare
        Batterieentladung gedeckt wird.
        """
    )

    st.markdown(
        """
        ### Max. Leitung 24h [%]

        Die höchste Leitungsauslastung, die während des gesamten Tages auftritt. Mehr als 100 % auslastung ist nicht zulässig und verschlechtert den Grid Performancescore stark.
        """
    )

with metric_col2:
    st.markdown(
        """
        ### Stunden mit Überlast

        Anzahl der Stunden, in denen mindestens eine Leitung über 100 %
        ausgelastet ist.

        Ein Zielwert von **0 Stunden** bedeutet, dass während des gesamten Tages
        keine modellierte Leitungsgrenze überschritten wird.
        """
    )

   


st.divider()


# ============================================================

st.header("Schritt 3: Eine einzelne Stunde untersuchen")

st.markdown(
    """
    Nutze den Slider **Stunde des Tages**, um verschiedene Stunden zwischen
    0 und 23 Uhr auszuwählen.

    Untersuche stichprobenartig:

    - eine Nachtstunde,
    - eine Mittagsstunde,
    - eine Abendstunde.
    """
)

st.subheader("Stunde des Tages")

st.write(
    "Der Stundenslider verändert nicht den simulierten Tag. Er wählt lediglich "
    "die Stunde aus, die auf der Netzkarte, im Leitungsdiagramm und in den "
    "Live-Kennzahlen genauer dargestellt wird."
)

st.markdown(
    """
    Beim Verschieben des Reglers solltest du beobachten:

    1. Wie hoch ist der Anteil der Photovoltaikerzeugung?
    2. Wie hoch ist der Anteil der Winderzeugung?
    3. Wie hoch ist die maximale Leitungsauslastung?
    4. Lädt oder entlädt der Batteriespeicher?
    """
)


# ============================================================

st.header("Schritt 4: Wind- und PV-Ausbau testen")

wind_tab, pv_tab = st.tabs(["Wind", "Photovoltaik"])

with wind_tab:
    st.subheader("Wind [%]")

    st.write(
        "Dieser Slider skaliert die gesamte Windstromerzeugung des ausgewählten "
        "Tages. Wind an Land und Wind auf See werden gemeinsam verändert."
    )

    st.markdown(
        """
        - **0 %:** keine Windstromerzeugung
        - **100 %:** reale Windstromerzeugung
        - **150 %:** 50 % mehr Windstrom
        - **200 %:** doppelte Windstromerzeugung
        - **300 %:** dreifache Windstromerzeugung
        """
    )

    st.markdown(
        """
        **Experiment**

        1. Notiere den aktuellen KPI.
        2. Erhöhe Wind um 25 oder 50 Prozentpunkte.
        3. Betrachte den neuen EE-Anteil.
        4. Prüfe die maximale Leitungsauslastung.
        5. Untersuche ob der Grid Performance Score gestiegen oder gesunken ist.
        """
    )

    st.info(
        "Mehr Windenergie erhöht häufig den EE-Anteil. Gleichzeitig muss die "
        "zusätzliche Energie von den windreichen Regionen zu den Verbrauchern "
        "transportiert werden."
    )

with pv_tab:
    st.subheader("PV [%]")

    st.write(
        "Dieser Slider skaliert die Photovoltaikerzeugung des ausgewählten Tages."
    )

    st.markdown(
        """
        - **0 %:** keine Photovoltaikerzeugung
        - **100 %:** reale Photovoltaikerzeugung
        - **150 %:** 50 % mehr Photovoltaik
        - **200 %:** doppelte Photovoltaikerzeugung
        - **300 %:** dreifache Photovoltaikerzeugung
        """
    )

    st.markdown(
        """
        **Experiment**

        1. Stelle Wind zunächst wieder auf den Ausgangswert.
        2. Erhöhe PV um 25 oder 50 Prozentpunkte.
        3. Betrachte besonders die Mittagsstunden.
        4. Prüfe, ob der Batteriespeicher lädt.
        5. Achte auf Überschüsse oder Abregelung.
        """
    )

    st.info(
        "PV erzeugt hauptsächlich tagsüber Strom. Ein sehr hoher PV-Ausbau kann "
        "deshalb mittags Überschüsse erzeugen, obwohl nachts weiterhin zusätzliche "
        "Erzeugung benötigt wird."
    )



st.divider()


# ============================================================

st.header("Schritt 5: Batteriespeicher einsetzen")

bess_col1, bess_col2 = st.columns(2)

with bess_col1:
    st.subheader("BESS Leistung/Energie [%]")

    st.write(
        "BESS bedeutet Battery Energy Storage System. Der Slider skaliert im "
        "Simulator gleichzeitig die Lade- und Entladeleistung sowie die "
        "verfügbare Speicherkapazität."
    )

    st.markdown(
        """
        - **0 %:** kein Batteriespeicher
        - **100 %:** Referenzgröße
        - **200 %:** doppelte Leistung und Speicherkapazität
        - **500 %:** fünffache Leistung und Speicherkapazität
        """
    )

with bess_col2:
    st.subheader("BESS Start-SOC [%]")

    st.write(
        "SOC bedeutet State of Charge und beschreibt den Ladezustand des "
        "Speichers zu Beginn des Tages."
    )

    st.markdown(
        """
        - **0 %:** Speicher vollständig leer
        - **50 %:** Speicher zur Hälfte geladen
        - **100 %:** Speicher vollständig geladen
        """
    )

st.markdown(
    """
    **Experiment**

    1. Erzeuge durch einen höheren Wind- oder PV-Wert zeitweise einen Überschuss.
    2. Vergleiche die Bilanz vor und nach BESS.
    3. Erhöhe anschließend die BESS-Größe.
    4. Prüfe, ob mehr Überschuss aufgenommen werden kann.
    5. Beobachte den SOC im Tagesverlauf.
    """
)

st.info(
    "Ein großer Speicher kann die Bilanz verbessern, erhöht aber auch den "
    "die Kosten eines Systems. Mehr Speicher ist daher nicht automatisch die beste Lösung."
)


st.divider()


# ============================================================

st.header("Schritt 6: Einen Netzengpass beheben")

st.subheader("Leitungskapazität / Netzausbau [%]")

st.write(
    "Dieser Slider skaliert die Kapazität aller modellierten Leitungen. "
    "Er stellt einen vereinfachten Ausbau des gesamten Übertragungsnetzes dar."
)

st.markdown(
    """
    - **50 %:** halbe Leitungskapazität
    - **100 %:** ursprüngliche Leitungskapazität
    - **200 %:** doppelte Leitungskapazität
    """
)

st.markdown(
    """
    **Experiment**

    1. Erzeuge zunächst durch mehr Wind oder PV eine Leitungsüberlastung.
    2. Erhöhe den Netzausbau in kleinen Schritten.
    3. Stoppe, sobald die Leitungsauslastung ausreichend reduziert wurde.
    4. Prüfe ob der Grid Performance Score gestiegen oder gefallen ist.
    """
)

st.info(
    "Verändere den Netzausbau möglichst in kleinen Schritten. Ein unnötig hoher "
    "Ausbau kann den Grid Performance Score trotz sicherer Leitungen verschlechtern."
)

st.caption(
    "In der Realität würden einzelne Leitungen gezielt ausgebaut. Der globale "
    "Slider ist eine didaktische Vereinfachung."
)



st.divider()


# ============================================================

st.header("Schritt 7: Eine eigene Lösung optimieren")

st.markdown(
    """
    Versuche nun, das ausgewählte Szenario vollständig zu lösen.

    Gehe dabei iterativ vor:

    1. Erhöhe Wind oder PV nur in kleinen Schritten.
    2. Prüfe nach jeder Änderung den 24h-EE-Anteil.
    3. Kontrolliere die maximale Leitungsauslastung.
    4. Nutze Speicher für zeitliche Überschüsse.
    5. Baue das Netz nur so weit aus wie erforderlich.
    6. Vergleiche nach jeder Änderung den Grid Performance Score.
    """
)

goal_col1, goal_col2, goal_col3 = st.columns(3)

with goal_col1:
    st.metric(
        label="Ziel 1",
        value="Hoher EE-Anteil",
        help="Wind, PV und Speicher sollen möglichst viel Last decken.",
    )

with goal_col2:
    st.metric(
        label="Ziel 2",
        value="Sicherheit",
        help="Keine Überlastung: Leitungen sollen während des gesamten Tages unter 100 % bleiben.",
    )

with goal_col3:
    st.metric(
        label="Ziel 3",
        value="Effizienz",
        help="Es sollte möglichst effizient ausgebaut werden, also möglichst wenig Erneuerbare Überproduktion welche zu Abregelung führt.",
    )


st.divider()


# ============================================================
# Diagrammreferenz
# ============================================================

st.header("Was zeigen die Diagramme?")

map_tab, line_tab, line_tab_max, dispatch_tab = st.tabs(
    [
        "Netzkarte",
        "Leitungsauslastung der aktuellen Stunde",
        "Maximale Leitungsauslastung des Tages",
        "Erzeugungsmix",
    ]
)

with map_tab:
    st.subheader("Netzkarte")
    generators=st.session_state.get("tut_generators", pd.DataFrame()),
    consumers=st.session_state.get("tut_consumers", pd.DataFrame()),
    line_status=st.session_state.get("tut_line_status", pd.DataFrame()),
    hour_row=st.session_state.get("tut_hour_row", pd.DataFrame()),
    wind_scale=st.session_state.get("tut_wind_scale", pd.DataFrame()),
    pv_scale=st.session_state.get("tut_pv_scale", pd.DataFrame()),
    konv_scale=st.session_state.get("tut_konv_scale", pd.DataFrame()),
    bess_scale=st.session_state.get("tut_bess_scale", pd.DataFrame()),
    refs=st.session_state.get("tut_refs", pd.DataFrame()),
    st.plotly_chart(
        build_map(
            generators=generators,
            consumers=consumers,
            lines=line_status,
            hour_row=hour_row,
            wind_scale=wind_scale,
            pv_scale=pv_scale,
            konv_scale=konv_scale,
            bess_scale=bess_scale,
            refs=refs,
        ),
        width="stretch",
    )
    st.write(
        "Die Netzkarte zeigt Erzeuger, Verbraucher, Batteriespeicher und "
        "Leitungen für die ausgewählte Stunde."
    )

    st.markdown(
        """
        **Leitungsfarben**

        - 🟢 Grün: weniger als 90 % ausgelastet
        - 🟠 Orange: mindestens 90 %, aber nicht über 100 %
        - 🔴 Rot: über 100 % ausgelastet
        """
    )

    st.markdown(
        """
        **Symbole**

        - Dreieck: Wind
        - Quadrat: Photovoltaik
        - Raute: Batteriespeicher
        - Kreis: restliche regelbare Erzeugung
        - Stern: Verbrauchercluster
        """
    )

    st.write(
        "Die Größe der Symbole hängt von der aktuellen Erzeugung oder dem "
        "aktuellen Verbrauch ab."
    )

    st.info(
        "Bewege den Mauszeiger über eine Leitung, um Kapazität, Leistungsfluss "
        "und prozentuale Auslastung anzuzeigen."
    )

with line_tab:
    st.subheader("Leitungsauslastung")

    st.write(
        "Das Balkendiagramm zeigt die Auslastung aller Leitungen in der "
        "ausgewählten Stunde."
    )

    st.markdown(
        """
        - Die Balken sind nach Auslastung sortiert.
        - Die rote gestrichelte Linie markiert 100 %.
        - Der höchste Balken zeigt den aktuell größten Netzengpass.
        """
    )

    st.info(
        "Ein Wert über 100 % bedeutet, dass der berechnete Leistungsfluss "
        "größer als die im Modell verfügbare Leitungskapazität ist."
    )

with line_tab_max:
    st.subheader("Maximale Leitungsauslastung")

    st.write(
        "Das Balkendiagramm zeigt die maximale Leitungsauslastung jeder Stunde "
        "des Tages."
    )

    
    st.info(
        "Ein Wert über 100 % bedeutet, dass der berechnete Leistungsfluss "
        "größer als die im Modell verfügbare Leitungskapazität ist."
    )

with dispatch_tab:
    st.subheader("Dispatch und Erzeugungsmix")

    st.write(
        "Das Diagramm zeigt für jede Stunde, durch welche Technologien der "
        "Stromverbrauch gedeckt wird."
    )

    st.markdown(
        """
        **Positive Balken**

        - Wind
        - Photovoltaik
        - restliche regelbare Erzeuger
        - BESS-Entladung

        **Negative Balken**

        - BESS-Ladung
        - Abregelung erneuerbarer Energie

        **Schwarze Linie**

        Stromverbrauch beziehungsweise Ziel-Last.

        **Gepunktete graue Linie**

        Rechnerisch benötigte restliche Erzeugung vor Berücksichtigung der Limits.
        """
    )


# ============================================================
# Weitere Kennzahlen
# ============================================================

st.header("Weitere Kennzahlen")

with st.expander("Kennzahlen der ausgewählten Stunde", expanded=False):
    st.markdown(
        """
        **Last/Ziel [GW]**  
        Stromverbrauch in der ausgewählten Stunde.

        **Wind [GW] und PV [GW]**  
        Aktuelle erneuerbare Erzeugungsleistung.

        **Restl. Erz. [GW]**  
        Aktuell eingesetzte regelbare restliche Erzeugung.

        **BESS [GW]**  
        Positiv bedeutet Entladung, negativ bedeutet Ladung.

        **Ziellücke nach EE**  
        Last abzüglich Wind- und PV-Erzeugung.

        **Restl. verfügbar [GW]**  
        Maximal verfügbare Leistung der restlichen Erzeuger.

        **Ziellücke vor BESS**  
        Verbleibende Differenz vor dem Einsatz des Batteriespeichers.

        **SOC [%]**  
        Aktueller Ladezustand des Batteriespeichers.

        **Abregelung**  
        Erneuerbare Erzeugung, die nicht verwendet werden kann.

        """
    )


# ============================================================
# Abschluss
# ============================================================

st.divider()



st.page_link(
    "app.py",
    label="Zurück zum Simulator",
    icon="🎮",
)