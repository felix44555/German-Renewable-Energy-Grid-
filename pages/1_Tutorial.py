import streamlit as st
import pandas as pd
from visualization import build_line_utilization_chart, build_line_utilization_chart_24h, build_map, build_stack #build_balance_chart,
from texts_tut import TXT_Tut # oder wo auch immer du das Dictionary abspeicherst

lang = st.session_state.get("lang", "DE") 

st.set_page_config(
    page_title=TXT_Tut[lang]["Page_Title"],
    page_icon="📘",
    layout="wide",
)

# ============================================================
# Kopfbereich
# ============================================================

st.title(TXT_Tut[lang]["Tut_Title"])

st.write(TXT_Tut[lang]["Tut_Intro"])

st.info(TXT_Tut[lang]["Tut_Goal"])


navigation_col1, navigation_col2 = st.columns(2)

with navigation_col1:
    st.page_link(
        "app.py",
        label=TXT_Tut[lang]["Nav_Sim"],
        icon="🎮",
    )

with navigation_col2:
    st.page_link(
        "pages/2_About.py",
        label=TXT_Tut[lang]["Nav_Model"],
        icon="📖",
    )


# ============================================================
# Tutorial-Ablauf
# ============================================================

st.header(TXT_Tut[lang]["Step1_Header"])

st.markdown(TXT_Tut[lang]["Step1_Text"])

with st.expander(TXT_Tut[lang]["Step1_Expander_Title"], expanded=True):
    st.markdown(TXT_Tut[lang]["Step1_Expander_Text"])


# ============================================================

st.header(TXT_Tut[lang]["Step2_Header"])

st.markdown(TXT_Tut[lang]["Step2_Text"])

metric_col1, metric_col2 = st.columns(2)

with metric_col1:
    st.markdown(TXT_Tut[lang]["Step2_Score"])
    st.markdown(TXT_Tut[lang]["Step2_EE"])
    
with metric_col2:
    st.markdown(TXT_Tut[lang]["Step2_MaxLine"])
    st.markdown(TXT_Tut[lang]["Step2_Overload"])
    

st.divider()

# ============================================================

st.header(TXT_Tut[lang]["Step3_Header"])

st.markdown(TXT_Tut[lang]["Step3_Text"])

st.subheader(TXT_Tut[lang]["Step3_Subheader"])

st.write(TXT_Tut[lang]["Step3_SliderText"])

st.markdown(TXT_Tut[lang]["Step3_Observe"])


# ============================================================

st.header(TXT_Tut[lang]["Step4_Header"])

wind_tab, pv_tab = st.tabs([TXT_Tut[lang]["Tab_Wind"], TXT_Tut[lang]["Tab_PV"]])

with wind_tab:
    st.subheader(TXT_Tut[lang]["Step4_Wind_Subheader"])
    st.write(TXT_Tut[lang]["Step4_Wind_Text"])
    st.markdown(TXT_Tut[lang]["Step4_Wind_Bullets"])
    st.markdown(TXT_Tut[lang]["Step4_Wind_Experiment"])
    st.info(TXT_Tut[lang]["Step4_Wind_Info"])

with pv_tab:
    st.subheader(TXT_Tut[lang]["Step4_PV_Subheader"])
    st.write(TXT_Tut[lang]["Step4_PV_Text"])
    st.markdown(TXT_Tut[lang]["Step4_PV_Bullets"])
    st.markdown(TXT_Tut[lang]["Step4_PV_Experiment"])
    st.info(TXT_Tut[lang]["Step4_PV_Info"])

st.divider()

# ============================================================

st.header(TXT_Tut[lang]["Step5_Header"])

bess_col1, bess_col2 = st.columns(2)

with bess_col1:
    st.subheader(TXT_Tut[lang]["Step5_BessPower"])
    st.write(TXT_Tut[lang]["Step5_BessPower_Text"])
    st.markdown(TXT_Tut[lang]["Step5_BessPower_Bullets"])

with bess_col2:
    st.subheader(TXT_Tut[lang]["Step5_BessSOC"])
    st.write(TXT_Tut[lang]["Step5_BessSOC_Text"])
    st.markdown(TXT_Tut[lang]["Step5_BessSOC_Bullets"])

st.markdown(TXT_Tut[lang]["Step5_Experiment"])

st.info(TXT_Tut[lang]["Step5_Info"])


st.divider()

# ============================================================

st.header(TXT_Tut[lang]["Step6_Header"])

st.subheader(TXT_Tut[lang]["Step6_Grid_Subheader"])

st.write(TXT_Tut[lang]["Step6_Grid_Text"])

st.markdown(TXT_Tut[lang]["Step6_Grid_Bullets"])

st.markdown(TXT_Tut[lang]["Step6_Experiment"])

st.info(TXT_Tut[lang]["Step6_Info"])

st.caption(TXT_Tut[lang]["Step6_Caption"])


st.divider()

# ============================================================

st.header(TXT_Tut[lang]["Step7_Header"])

st.markdown(TXT_Tut[lang]["Step7_Text"])

goal_col1, goal_col2, goal_col3 = st.columns(3)

with goal_col1:
    st.metric(
        label=TXT_Tut[lang]["Goal1"],
        value=TXT_Tut[lang]["Goal1_Val"],
        help=TXT_Tut[lang]["Goal1_Help"],
    )

with goal_col2:
    st.metric(
        label=TXT_Tut[lang]["Goal2"],
        value=TXT_Tut[lang]["Goal2_Val"],
        help=TXT_Tut[lang]["Goal2_Help"],
    )

with goal_col3:
    st.metric(
        label=TXT_Tut[lang]["Goal3"],
        value=TXT_Tut[lang]["Goal3_Val"],
        help=TXT_Tut[lang]["Goal3_Help"],
    )

st.divider()

# ============================================================
# Diagrammreferenz
# ============================================================

# Werte werden aus session state geholt
generators=st.session_state.get("tut_generators", pd.DataFrame())
consumers=st.session_state.get("tut_consumers", pd.DataFrame())
line_status=st.session_state.get("tut_line_status", pd.DataFrame())
hour_row=st.session_state.get("tut_hour_row", pd.Series(dtype=float))
wind_scale=st.session_state.get("tut_wind_scale", 1.0)
pv_scale=st.session_state.get("tut_pv_scale", 1.0)
konv_scale=st.session_state.get("tut_konv_scale", 1.0)
bess_scale=st.session_state.get("tut_bess_scale", 1.0)
refs=st.session_state.get("tut_refs", {})
line_status_24h = st.session_state.get("tut_line_status_24h", {})
df = st.session_state.get("tut_df", pd.DataFrame())
hour = st.session_state.get("tut_hour", 12)

# C-Analogie: if (ptr == NULL) -> goto main
if "tut_df" not in st.session_state or st.session_state.get("tut_df", pd.DataFrame()).empty:
    st.warning(TXT_Tut[lang]["Warning_NoData"])
    st.switch_page("app.py") # Bricht hier ab und lädt sofort die Hauptseite neu!
    st.stop() # Sicherheitsabbruch, damit der restliche Code auf dieser Seite nicht crasht

st.header(TXT_Tut[lang]["Charts_Header"])

map_tab, line_tab, line_tab_max, dispatch_tab = st.tabs(
    [
        TXT_Tut[lang]["Tab_Map"],
        TXT_Tut[lang]["Tab_Line"],
        TXT_Tut[lang]["Tab_Line_Max"],
        TXT_Tut[lang]["Tab_Dispatch"],
    ]
)

with map_tab:
    st.subheader(TXT_Tut[lang]["Chart_Map_Sub"])
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
    st.write(TXT_Tut[lang]["Chart_Map_Text1"])
    st.markdown(TXT_Tut[lang]["Chart_Map_Colors"])
    st.markdown(TXT_Tut[lang]["Chart_Map_Symbols"])
    st.write(TXT_Tut[lang]["Chart_Map_Text2"])
    st.info(TXT_Tut[lang]["Chart_Map_Info"])

with line_tab:
    st.subheader(TXT_Tut[lang]["Chart_Line_Sub"])
    st.plotly_chart(build_line_utilization_chart(line_status), width="stretch")
    st.write(TXT_Tut[lang]["Chart_Line_Text1"])
    st.markdown(TXT_Tut[lang]["Chart_Line_Bullets"])
    st.info(TXT_Tut[lang]["Chart_Line_Info"])

with line_tab_max:
    st.subheader(TXT_Tut[lang]["Chart_LineMax_Sub"])
    st.plotly_chart(build_line_utilization_chart_24h(line_status_24h), width="stretch")  
    st.write(TXT_Tut[lang]["Chart_LineMax_Text"])
    st.info(TXT_Tut[lang]["Chart_Line_Info"])

with dispatch_tab:
    st.subheader(TXT_Tut[lang]["Chart_Dispatch_Sub"])
    st.plotly_chart(build_stack(df, highlight_hour=int(hour)), width="stretch")
    st.write(TXT_Tut[lang]["Chart_Dispatch_Text1"])
    st.markdown(TXT_Tut[lang]["Chart_Dispatch_Bullets"])

# ============================================================
# Weitere Kennzahlen
# ============================================================

st.header(TXT_Tut[lang]["Metrics_Header"])

with st.expander(TXT_Tut[lang]["Metrics_Expander"], expanded=False):
    st.markdown(TXT_Tut[lang]["Metrics_Text"])


# ============================================================
# Abschluss
# ============================================================

st.divider()

st.page_link(
    "app.py",
    label=TXT_Tut[lang]["Footer_Back"],
    icon="🎮",
)