from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import copy

from dc_powerflow import compute_dc_line_status, find_max_line_utilization_24h
from dispatch import generate_synthetic_profiles, prepare_dispatch_profiles
from grid_io import (
    ensure_bess_visible,
    get_reference_values,
    load_pypsa_network,
    pypsa_to_consumers,
    pypsa_to_generators,
    pypsa_to_lines,
)
from scenarios import SCENARIOS, apply_scenario_to_profiles, evaluate_scenario
from smard_api import load_smard_api_profile
from visualization import build_line_utilization_chart, build_line_utilization_chart_24h, build_map, build_stack #build_balance_chart,
from KPI_code import _calculate_24h_kpi,_calculate_current_kpi

BASE_DIR = Path(__file__).resolve().parent
NETWORK_FILE = BASE_DIR / "real_germany_8n.nc"
APP_VERSION = "modular-smard-api-dc-safe-1"


def _format_gap(value: float) -> str:
    ''' input float, return Wert string'''
    if value > 0:
        return f"Unterdeckung {value:.2f} GW"
    if value < 0:
        return f"Überdeckung {abs(value):.2f} GW"
    return "ausgeglichen"


def _clean_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Streamlit/Arrow kann DataFrame.attrs mit DataFrame-Inhalt nicht serialisieren."""
    out = df.copy()
    out.attrs = {}
    return out



@st.cache_resource(show_spinner=False)
def _cached_network(path_str: str, mtime_ns: int):
    return load_pypsa_network(path_str)
#@... sorgt dafür das die funtion nicht jedes mal neu ausgeführt wird.'''

@st.cache_data(ttl=3600, show_spinner="Lade SMARD-Orientierungsdaten ...")
def _cached_smard_profile(day_iso: str, region: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    return load_smard_api_profile(day_iso, region=region)
#ebenfalls wird funktion nicht jedes mal geladen, zeitlich jedoch auf 3600s begrenztz (STunde)'''

@st.dialog("Knoten-Erzeugung anpassen")
def node_adjustment_modal(node_index):
    st.write(f"Du bearbeitest den Wind-Knoten mit der ID: {node_index}")
    
    # Hier kommt dein UI für den einzelnen Knoten rein
    neuer_wert = st.slider("Lokale Wind-Erzeugung [%]", 0, 100, 100)
    
    if st.button("Speichern & Berechnen"):
        # 1. Wert in den globalen Speicher schreiben
        st.session_state[f"wind_node_{node_index}"] = neuer_wert
        
        # 2. Modal schließen und Rerun triggern
        st.rerun()

def _load_network_tables() -> tuple[Any, dict[str, float], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if not NETWORK_FILE.exists():
        raise FileNotFoundError(f"Netzdatei nicht gefunden: {NETWORK_FILE.name}")
    n = _cached_network(str(NETWORK_FILE), NETWORK_FILE.stat().st_mtime_ns)
    #sorgt dafür das Netzdatei bei Änderung neu geladen wird
    refs = get_reference_values(n)
    consumers = pypsa_to_consumers(n)
    generators = ensure_bess_visible(pypsa_to_generators(n), consumers)
    lines = pypsa_to_lines(n)
    #extrahiert Pypsa Netzdaten in Panda Frames zur besseren verwendbarkeit in Streamlit'''
    return n, refs, consumers, generators, lines


def init_session_state() -> None:
    st.session_state.setdefault("scenario_key", "training")
    #durch set default weden startwerte nur beim erstmaligen lafen gesetzt'''
    scenario = SCENARIOS.get("training", {})
    defaults = dict(scenario.get("defaults", {}))
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    st.session_state.setdefault("data_just_loaded", True)


def load_scenario_defaults(scenario_key: str) -> None:
    scenario = SCENARIOS.get(scenario_key, SCENARIOS["training"])
    for key, value in scenario.get("defaults", {}).items():
        st.session_state[key] = value
def on_scenario_change():
    load_scenario_defaults(st.session_state["scenario_key"])
    st.session_state["data_just_loaded"] = True
def on_date_change():
    st.session_state["data_just_loaded"] = True
    reset_slider()
def reset_slider():
    st.header("Stellgrößen")
    st.session_state["wind_pct"]=100
    st.session_state["pv_pct"]=100
    st.session_state["bess_pct"]=100
    st.session_state["soc_pct"]=50
    st.session_state["line_capacity_pct"]=100
    
def main() -> None:
    st.set_page_config(page_title="Deutschland-Netzkarte: SMARD + DC-Lastfluss", layout="wide")
    init_session_state()
    # --- TUTORIAL BANNER START ---
    
    with st.container():
    
        st.info("👋 Neu im Simulator? Lerne die Grundlagen der Netzbalance in unserem Tutorial.")
    
        st.page_link("pages/1_Tutorial.py", label="Zum Tutorial")
    
        st.divider()

    # --- TUTORIAL BANNER END ---
    st.title("Deutschland-Netzkarte: SMARD-API, regelbare Restleistung und DC-Lastfluss")
    st.markdown(
        "SMARD wird nur für Netzlast, Wind und PV genutzt. Externe Importe/Exporte und SMARD-Restkategorien "
        "werden nicht geladen. Die restlichen Erzeuger werden künstlich als konventionelle Erzeuger netzstützend modelliert."# Die restlichen Erzeuger werden künstlich als regelbare Leistung aus der .nc-/Fallback-Kapazität modelliert."
    )
    #st.caption(
     #   f"Version: {APP_VERSION}. Module: smard_api.py, dispatch.py, grid_io.py, dc_powerflow.py, visualization.py, scenarios.py. "
     #  "Leitungsauslastung wird mit einer DC-Lastfluss-Näherung gerechnet."
    #)

    try:
        _, refs, consumers, generators, lines = _load_network_tables()
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    with st.sidebar:
        st.header("Szenario")
        scenario_key = st.selectbox(
            "Aufgabe",
            options=list(SCENARIOS.keys()),
            format_func=lambda k: SCENARIOS[k].get("name", k),
            key="scenario_key",
            on_change = on_scenario_change,
        )
        scenario = SCENARIOS[scenario_key]
        st.info(str(scenario.get("task", "")))
        #if st.button("Szenario-Startwerte laden"): #Button zum laden ersetzt
         #   load_scenario_defaults(scenario_key)
         #   st.rerun()

        st.header("Datenquelle")
        #profile_source = st.radio(
        #    "Zeitreihe",
        #    options=["SMARD-API", "synthetisch"],
        #    index=0,
        #    help="SMARD lädt nur Netzlast, Wind Offshore/Onshore und PV. Restliche Erzeuger kommen nicht aus SMARD.",
        #)
        profile_source = "SMARD-API"
        current_date = st.session_state.get("smard_day", date.today() - timedelta(days=2))
        is_locked = st.session_state.get("date_locked", True)
        
        
        st.session_state["smard_day"] = current_date
        
        smard_day = st.date_input(
            "SMARD-Datum",
            value = current_date,
            min_value=date(2015, 1, 1),
            max_value=date.today() - timedelta(days=2),
            disabled=is_locked,
            on_change = on_date_change,
            help="Sehr aktuelle Tage können noch unvollständige SMARD-Daten haben.",
        )
        if not is_locked:
            st.session_state["smard_day"] = smard_day
        #!!!!!!!!!!!!!!!!!!!!!!!!!!!!min Date anpassen!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!'''
        #region = st.selectbox("SMARD-Region", options=["DE", "50Hertz", "Amprion", "TenneT", "TransnetBW"], index=0)
        region = "DE"
        
        st.header("Stellgrößen")
        wind_pct = st.slider("Wind [% der SMARD-Orientierung]", 0, 300, key="wind_pct", step=5)
        pv_pct = st.slider("PV [% der SMARD-Orientierung]", 0, 300, key="pv_pct", step=5)
        #konv_pct = st.slider("Restliche Erzeuger verfügbare Leistung [%]", 0, 250, key="konv_pct", step=5, help="Skaliert die verfügbare regelbare Leistung aus .nc/Fallback. Nicht SMARD-gekoppelt.",)
        konv_pct = 100.0
        #konv_min_pct = st.slider("Restliche Erzeuger Mindestbetrieb [% verfügbar]", 0, 80, key="konv_min_pct", step=5, help="0 % bedeutet vollständig herunterfahrbar. Höhere Werte erzeugen bei viel EE eher Überschuss.",)
        konv_min_pct = 0.0
        bess_pct = st.slider("BESS Leistung/Energie [%]", 0, 500, key="bess_pct", step=5)
        #load_pct = st.slider("Last/Ziel [% der SMARD-Last]", 50, 200, key="load_pct", step=5)
        load_pct = st.session_state["load_pct"] 
        soc_pct = st.slider("BESS Start-SOC [%]", 0, 100, key="soc_pct", step=5)
        #st.info(str(load_pct))
        st.header("Netz- und EE-Maßnahmen")
        line_capacity_pct = st.slider("Leitungskapazität / Netzausbau [%]", 50, 200, key="line_capacity_pct", step=5)
        ee_curtail_pct = 100.0
        
        #st.caption(
         #   f"Referenzwerte aus Netz/Fallback:\n"
         #   f"- Wind: {refs['wind_gw']:.2f} GW\n"
         #   f"- PV: {refs['pv_gw']:.2f} GW\n"
         #   f"- Restliche Erzeuger: {refs['konv_gw']:.2f} GW\n"
         #   f"- BESS: {refs['bess_gw']:.2f} GW / {refs['bess_gwh']:.2f} GWh\n"
         #   f"- mittlere Netzlast: {refs['load_mean_gw']:.2f} GW"
        #)

    wind_scale = wind_pct / 100.0
    pv_scale = pv_pct / 100.0
    konv_scale = konv_pct / 100.0
    bess_scale = bess_pct / 100.0
    load_scale = load_pct / 100.0

    api_meta = pd.DataFrame()
    if profile_source == "SMARD-API":
        try:
            base_profiles, api_meta = _cached_smard_profile(smard_day.isoformat(), region)
        except Exception as exc:
            st.error(f"SMARD-API-Daten konnten nicht geladen werden: {exc}")
            st.info("Prüfe Internetzugang, Datum und requirements.txt. Für Offline-Demo kann die synthetische Quelle genutzt werden.")
            st.stop()
    else:
        base_profiles = generate_synthetic_profiles(refs)

    scenario_profiles = apply_scenario_to_profiles(base_profiles, scenario_key=scenario_key, ee_curtail_pct=0.0)
    df = prepare_dispatch_profiles(
        scenario_profiles,
        wind_scale=wind_scale,
        pv_scale=pv_scale,
        konv_scale=konv_scale,
        load_scale=load_scale,
        bess_scale=bess_scale,
        refs=refs,
        soc_start_pct=soc_pct,
        ee_curtail_pct=ee_curtail_pct,
        konv_min_pct=konv_min_pct,
    )
    
    hour = st.session_state.get("hour", 0)
    hour_row = df.iloc[int(hour)]
    
    line_status = compute_dc_line_status(
        generators=generators,
        consumers=consumers,
        lines=lines,
        hour_row=hour_row,
        line_capacity_pct=line_capacity_pct,
        line_stress_factor=float(SCENARIOS[scenario_key].get("line_stress_factor", 1.0)),
    )
    nodal_status = line_status.attrs.get("dc_nodal_status", pd.DataFrame())
    scenario_eval = evaluate_scenario(hour_row=hour_row, line_status=line_status, scenario_key=scenario_key)
    kpi_hour = _calculate_current_kpi(
        hour_row=hour_row,
        line_status=line_status,
        wind_pct=wind_pct,
        pv_pct=pv_pct,
        bess_pct=bess_pct,
        line_capacity_pct=line_capacity_pct,
    )
    
    line_status_24h = {}
    # 2. Wir berechnen den Lastfluss für JEDE Stunde des Tages
    for stunde_idx, row in df.iterrows():
        line_status_24h[stunde_idx] = compute_dc_line_status(
            generators=generators,
            consumers=consumers,
            lines=lines,
            hour_row=row, # <-- Hier übergeben wir die jeweilige Stunde aus der Schleife
            line_capacity_pct=line_capacity_pct,
            line_stress_factor=float(SCENARIOS[scenario_key].get("line_stress_factor", 1.0)),
        )
    kpi_24h = _calculate_24h_kpi(
        df=df,
        generators=generators,
        consumers=consumers,
        lines=lines,
        wind_pct=wind_pct,
        pv_pct=pv_pct,
        bess_pct=bess_pct,
        line_capacity_pct=line_capacity_pct,
        line_stress_factor=float(SCENARIOS[scenario_key].get("line_stress_factor", 1.0)),
        line_status=line_status_24h,  
    )
    
    if st.session_state.get("data_just_loaded", False):
        hour=find_max_line_utilization_24h(line_status_24h)
        st.session_state["hour"]=hour
        
        st.session_state["start_kpi_hour"] = copy.deepcopy(kpi_hour)
        st.session_state["start_kpi_24h"] = copy.deepcopy(kpi_24h)
        
        st.session_state["data_just_loaded"]=False
     
    start_kpi_hour = st.session_state.get("start_kpi_hour", {"kpi": 0.0})
    start_kpi_24h = st.session_state.get("start_kpi_24h", {"kpi_24h": 0.0})
    #st.subheader("Szenario-Bewertung") #old dsplay

    #for msg in scenario_eval.get("messages", []): #old display
     #   st.write(f"- {msg}")
    
    st.subheader("24h Grid Performance Score")
    
    if bool(scenario_eval.get("solved", False)):
        st.success("Szenario bewältigt.")
    else:
        st.warning("Szenario noch nicht bewältigt.")
    
    kpi0, kpi1, kpi2, kpi3, kpi4, kpi7 = st.columns(6)
    kpi0.metric("Start Grid Performance Score", f"{start_kpi_24h['kpi_24h']:.2f}")
    kpi1.metric("Grid Performance Score", f"{kpi_24h['kpi_24h']:.2f}")
    kpi2.metric("24h EE-Anteil [%]", f"{kpi_24h['re_share_pct_24h']:.1f}")
    kpi3.metric("max. Leitung 24h [%]", f"{kpi_24h['max_line_load_24h']:.0f}")
    kpi4.metric("Stunden mit Überlast", str(kpi_24h["overloaded_hours"]))
    kpi7.metric(
        "Ausbau-Faktor",
        f"{kpi_24h['grid_added'] + kpi_24h['bat_added'] + kpi_24h['pv_added'] + kpi_24h['wind_added']:.2f}",
    )
    
    if kpi_24h["max_line_load_24h"] > 100.0:
        st.warning("Der Grid Performance Score wurde stark reduziert, weil im Tagesverlauf mindestens eine Leitung über 100 % ausgelastet ist.")  
    elif kpi_24h["kpi_24h"] >= 70:
        st.success("Hoher Grid Performance Score: hoher EE-Anteil bei moderatem Ausbau und ohne Leitungsüberlast.")
    elif kpi_24h["kpi_24h"] >= 40:
        st.info("Mittlerer Grid Performance Score: technisch brauchbar, aber Ausbau, EE-Anteil oder Netzbelastung sind nicht optimal.")
    else:
        st.warning("Niedriger Grid Performance Score: geringe technische Güte durch niedrigen EE-Anteil, hohen Ausbau oder Netzüberlast.")
# Übergabe in Session State um sie auf den anderen Unteseiten zu nutzen
    st.session_state["tut_generators"] = generators
    st.session_state["tut_consumers"] = consumers
    st.session_state["tut_line_status"] = line_status
    st.session_state["tut_hour_row"] = hour_row
    st.session_state["tut_wind_scale"] = wind_scale
    st.session_state["tut_pv_scale"] = pv_scale
    st.session_state["tut_konv_scale"] = konv_scale
    st.session_state["tut_bess_scale"] = bess_scale
    st.session_state["tut_refs"] = refs
    st.session_state["tut_line_status_24h"] = line_status_24h
    st.session_state["tut_df"] = df
    st.session_state["tut_hour"] = hour
    
    c_left, c_right = st.columns([1.2, 1.0])
    with c_left:
        st.subheader("Netzkarte")
       # st.plotly_chart(
       #     build_map(
       #         generators=generators,
       #         consumers=consumers,
       #         lines=line_status,
       #         hour_row=hour_row,
       #         wind_scale=wind_scale,
       #        pv_scale=pv_scale,
       #         konv_scale=konv_scale,
       #         bess_scale=bess_scale,
       #         refs=refs,
       #     ),
       #     width="stretch",
        #)
        ##########################ANFANG TEST###########################################
        # Statt st.plotly_chart(fig)
        # Nutze on_select="rerun", um bei jedem Klick das Skript neu zu laden
        event = st.plotly_chart(
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
               width="stretch", on_select="rerun")

        # Auswertung des Klicks
        if event and "selection" in event and event["selection"].get("points"):
            points = event["selection"]["points"]
            if len(points) > 0:
                clicked_point = points[0]
                
                # Lese curveNumber und pointIndex aus (wie Struct-Member-Zugriff in C)
                curve_number = clicked_point.get("curve_number")
                point_index = clicked_point.get("point_index")

                # FILTER: Nur wenn die curveNumber 14 (Wind) ist, speichern wir den Klick
                if curve_number == 24 and point_index is not None:
                    st.session_state["clicked_point_index"] = point_index
                    st.session_state["last_clicked_index"] = point_index # Für dein st.write unten
                
                # Optional: Wenn man auf etwas anderes (z.B. curve 15) klickt, 
                # heben wir die Wind-Auswahl wieder auf
                elif curve_number != 24:
                    st.session_state.pop("clicked_point_index", None)
                    st.session_state.pop("last_clicked_index", None)

        # Wenn Wind (14) geklickt wird -> Öffne das Pop-up!
        if "last_clicked_index" in st.session_state and point_index is not None:
            node_adjustment_modal(point_index)
        # Hier nun die Anzeige basierend auf dem State
        if "last_clicked_index" in st.session_state:
            st.write(f"Du hast den Wind-Knoten mit Index {st.session_state['last_clicked_index']} angeklickt!")    
        ####################################ENDE TEST####################################
        #st.subheader("Zeitslider")
        st.slider("Stunde des Tages", 0, 23, key="hour", step=1)
    with c_right:
        st.subheader("Leitungsauslastung")
        st.plotly_chart(build_line_utilization_chart(line_status), width="stretch")
        st.plotly_chart(build_line_utilization_chart_24h(line_status_24h), width="stretch")       
    #st.subheader("Bilanz und Erzeugungsmix")
    #st.plotly_chart(build_balance_chart(df, highlight_hour=int(hour)), width="stretch")
    st.plotly_chart(build_stack(df, highlight_hour=int(hour)), width="stretch")
    st.caption("Dispatch: (teilweise skalierte) SMARD-Last/Wind/PV + künstlich geregelte restliche Erzeuger")
    
       # ab hier runter
       #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
       #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
       #+++++++++++++++++++++++++++++++++AUSGEBLENDET AM SEITENENDE*+++++++++++++++++++++++++++++++++++++++
       #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
       #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    with st.expander("Modellannahmen"):
        st.write(
            "- Zielgröße ist die SMARD-Netzlast.\n"
            "- Wind = SMARD Wind Offshore + Wind Onshore.\n"
            "- PV = SMARD Photovoltaik.\n"
            "- Restliche Erzeuger werden nicht aus SMARD geladen, sondern künstlich auf die Residuallast gefahren.\n"
            "- Externe Importe, Exporte und kommerzielle Austauschflüsse werden nicht geladen.\n"
            "- BESS: positiv = Entladung, negativ = Ladung.\n"
            "- Leitungsauslastung: DC-Lastfluss-Näherung, kein vollständiger AC-Lastfluss."
        )
    
    with st.expander("Weitere Kennzahlen"):
        st.subheader("Ausführlich24h Engineering-Feasibility-KPI") 
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("24h-KPI", f"{kpi_24h['kpi_24h']:.2f}")
        kpi2.metric("24h EE-Anteil [%]", f"{kpi_24h['re_share_pct_24h']:.1f}")
        kpi3.metric("max. Leitung 24h [%]", f"{kpi_24h['max_line_load_24h']:.0f}")
        kpi4.metric("Stunden mit Überlast", str(kpi_24h["overloaded_hours"]))
        
        kpi5, kpi6, kpi7 = st.columns(3)
        kpi5.metric("24h Last [GWh]", f"{kpi_24h['total_load_gwh']:.1f}")
        kpi6.metric("24h Wind+PV [GWh]", f"{kpi_24h['total_re_gwh']:.1f}")
        kpi7.metric(
            "Ausbau-Faktor",
            f"{kpi_24h['grid_added'] + kpi_24h['bat_added'] + kpi_24h['pv_added'] + kpi_24h['wind_added']:.2f}",
        )
        
        
        st.subheader("Live-Kennzahlen")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Last/Ziel [GW]", f"{hour_row['Last_GW']:.2f}")
        k2.metric("Wind [GW]", f"{hour_row['Wind_GW']:.2f}")
        k3.metric("PV [GW]", f"{hour_row['PV_GW']:.2f}")
        k4.metric("Restl. Erz. [GW]", f"{hour_row['Konv_GW']:.2f}")
        #k6.metric("Bilanz [GW]", f"{hour_row['Netzbilanz_GW']:+.2f}")
    
        #b2, b3, b5 = st.columns(3)
        #b1.metric("Ziellücke nach EE", _format_gap(float(hour_row["Last_GW"] - hour_row["Wind_GW"] - hour_row["PV_GW"])))
        #b2.metric("Restl. Soll [GW]", f"{hour_row['Konv_Soll_GW']:.2f}")
        #b3.metric("Restl. verfügbar [GW]", f"{hour_row['Konv_Max_GW']:.2f}")
        #b4.metric("Ziellücke vor BESS", _format_gap(float(hour_row["Zielluecke_vor_BESS_GW"])))
        #b5.metric("SOC [%]", f"{hour_row['SOC_pct']:.1f}")
    
        c1, c2, c3, c4 = st.columns(4)
        #c1.metric("Konv. Fehlleistung", f"{hour_row['Konv_Fehlleistung_GW']:.2f} GW")
        #c2.metric("Mindestlauf-Überschuss", f"{hour_row['Konv_Mindestlauf_Ueberschuss_GW']:.2f} GW")
        c1.metric("BESS [GW]", f"{hour_row['BESS_GW']:+.2f}")
        c2.metric("SOC [%]", f"{hour_row['SOC_pct']:.1f}")
        c3.metric("Abregelung", f"{hour_row['Curtailment_GW']:.2f} GW")
        c4.metric("Status", str(hour_row["Status"]))
        st.subheader("Stündliche Engineering-Feasibility-KPI")
        
        kpi_cols = st.columns(4)
        kpi_cols[0].metric("Start Feasibility-KPI", f"{start_kpi_hour['kpi']:.2f}")
        kpi_cols[1].metric("Feasibility-KPI", f"{kpi_hour['kpi']:.2f}")
        kpi_cols[2].metric("EE-Anteil [%]", f"{kpi_hour['re_share_pct']:.1f}")
        #kpi_cols[2].metric("max. Leitung [%]", f"{kpi_hour['max_line_load']:.0f}")
        kpi_cols[3].metric(
            "Ausbau-Faktor",
            f"{kpi_hour['grid_added'] + kpi_hour['bat_added'] + kpi_hour['pv_added'] + kpi_hour['wind_added']:.2f}",
    )
        e2, e3, e4 = st.columns(3)
        #e1.metric("Bilanz [GW]", f"{scenario_eval.get('balance_gw', 0.0):+.2f}")
        e2.metric("Abregelung [GW]", f"{scenario_eval.get('curtailment_gw', 0.0):.2f}")
        e3.metric("max. Leitung [%]", f"{scenario_eval.get('peak_line_util_pct', 0.0):.0f}")
        e4.metric("überlastete Leitungen", str(scenario_eval.get("overloaded_count", 0)))
        #bis hier runter
    
    with st.expander("Stündliche Tabelle"):
        cols = [
            "Stunde", "Last_GW", "Wind_GW", "PV_GW", "Konv_Soll_GW", "Konv_Min_GW", "Konv_Max_GW",
            "Konv_GW", "Konv_Fehlleistung_GW", "Konv_Mindestlauf_Ueberschuss_GW",
            "Inlaendische_Erzeugung_GW", "Bilanz_vor_BESS_GW", "Zielluecke_vor_BESS_GW",
            "BESS_GW", "BESS_Laden_GW", "BESS_Entladen_GW", "Curtailment_GW",
            "SOC_GWh", "SOC_pct", "Netzbilanz_GW", "Status",
        ]
        st.dataframe(_clean_for_display(df[[c for c in cols if c in df.columns]].round(3)), width="stretch")

    with st.expander("SMARD-API Abrufe"):
        if api_meta.empty:
            st.write("Keine API-Metadaten, weil synthetische Quelle aktiv ist.")
        else:
            st.dataframe(_clean_for_display(api_meta), width="stretch")

    with st.expander("PyPSA-Erzeuger / Speicher"):
        st.dataframe(_clean_for_display(generators.round(4)), width="stretch")

    with st.expander("PyPSA-Verbraucher-Cluster"):
        st.dataframe(_clean_for_display(consumers.round(4)), width="stretch")

    with st.expander("PyPSA-Leitungen und DC-Lastfluss"):
        st.dataframe(_clean_for_display(line_status.round(4)), width="stretch")

    with st.expander("DC-Knotensalden und Winkel"):
        if isinstance(nodal_status, pd.DataFrame) and not nodal_status.empty:
            st.dataframe(_clean_for_display(nodal_status.round(4)), width="stretch")
        else:
            st.write("Keine Knotensalden verfügbar.")

    #with st.expander("Netz-Referenzwerte"):
     #   st.json(refs)

    #st.caption(
    #    "Topologie und räumliche Verteilung kommen aus real_germany_8n.nc. "
    #    "Zeitreihen kommen bei SMARD-API-Modus nur für Last/Wind/PV direkt von SMARD. "
    #    "Restliche Erzeuger sind regelbare Modellleistung. Die App löst kein PyPSA-Optimierungsproblem."
    #)



if __name__ == "__main__":
    main()