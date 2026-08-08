import streamlit as st
from texts import TXT_Abt 

lang = st.session_state.get("lang", "DE") 
st.set_page_config(page_title="About", layout="wide")

with st.sidebar:
    st.header(TXT_Abt[lang]["Abt_Sprache"])
    # Der gewählte Wert in "options" kann DE/EN bleiben, wir steuern nur die Anzeige nicht unbedingt.
    st.radio("Sprache / Language", options=["DE", "EN"], key="lang")
    lang = st.session_state.get("lang", "DE")
    st.divider()
    
st.title(TXT_Abt[lang]["Abt_Title"])
st.write(TXT_Abt[lang]["Abt_Intro"])

st.divider()

# 1. Was ist diese Website?
st.header(TXT_Abt[lang]["Abt_Sec1_Title"])
st.write(TXT_Abt[lang]["Abt_Sec1_Text"])

# 2. Was ist das Übertragungsnetz?
st.header(TXT_Abt[lang]["Abt_Sec2_Title"])
st.write(TXT_Abt[lang]["Abt_Sec2_Text"])

# 3. Herausforderungen des Netzes
st.header(TXT_Abt[lang]["Abt_Sec3_Title"])
with st.container():
    st.markdown(TXT_Abt[lang]["Abt_Sec3_Text"])

# 4. Ziel der Simulation (KPIs)
st.header(TXT_Abt[lang]["Abt_Sec4_Title"])
st.info(TXT_Abt[lang]["Abt_Sec4_Info"])

c1, c2, c3 = st.columns(3)

with c1:
    st.subheader(TXT_Abt[lang]["Abt_Sec4_Sub1"])
    st.write(TXT_Abt[lang]["Abt_Sec4_Text1"])
with c2:
    st.subheader(TXT_Abt[lang]["Abt_Sec4_Sub2"])
    st.write(TXT_Abt[lang]["Abt_Sec4_Text2"])
with c3:
    st.subheader(TXT_Abt[lang]["Abt_Sec4_Sub3"])
    st.write(TXT_Abt[lang]["Abt_Sec4_Text3"])

# 5. Wie funktioniert die Lastflussrechnung?
st.header(TXT_Abt[lang]["Abt_Sec5_Title"])

st.markdown(TXT_Abt[lang]["Abt_Sec5_Sub1"])
st.markdown(TXT_Abt[lang]["Abt_Sec5_Text1"])

st.markdown(TXT_Abt[lang]["Abt_Sec5_List1"])
st.latex(r"|V| \approx 1\,pu")

st.markdown(TXT_Abt[lang]["Abt_Sec5_List2"])
st.latex(r"R \ll X")

st.markdown(TXT_Abt[lang]["Abt_Sec5_List3"])
st.latex(r"\sin(\theta_a-\theta_b)\approx\theta_a-\theta_b")

st.markdown(TXT_Abt[lang]["Abt_Sec5_List4"])

st.divider()

st.markdown(TXT_Abt[lang]["Abt_Sec5_Sub2"])
st.markdown(TXT_Abt[lang]["Abt_Sec5_Text2"])

st.latex(
    r"P_{ab}\approx\frac{\theta_a-\theta_b}{x_{ab}}"
)

st.markdown(TXT_Abt[lang]["Abt_Sec5_Text3"])
st.markdown(TXT_Abt[lang]["Abt_Sec5_Text4"])

st.latex(r"b_{ab}=\frac{1}{x_{ab}}")
st.latex(r"P_{ab}=b_{ab}(\theta_a-\theta_b)")

st.divider()

st.markdown(TXT_Abt[lang]["Abt_Sec5_Sub3"])
st.markdown(TXT_Abt[lang]["Abt_Sec5_Text5"])

st.latex(
    r"P_m=\sum_{n\in N(m)}\frac{\theta_m-\theta_n}{x_{mn}}"
)

st.markdown(TXT_Abt[lang]["Abt_Sec5_Text6"])

st.divider()

with st.expander(TXT_Abt[lang]["Abt_Expander"], expanded=False):

    st.markdown(TXT_Abt[lang]["Abt_Exp_Sub1"])

    st.markdown(TXT_Abt[lang]["Abt_Exp_Text1"])

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.image(
            "pages/dc_3_knoten.jpeg",
            caption=TXT_Abt[lang]["Abt_Exp_Caption"],
            use_container_width=True
        )

    st.markdown(TXT_Abt[lang]["Abt_Exp_Text2"])

    st.latex(r"V_B=380\,\mathrm{kV}")
    st.latex(r"S_B=1000\,\mathrm{MVA}")

    st.markdown(TXT_Abt[lang]["Abt_Exp_Text3"])

    st.latex(
        r"Z_B=\frac{V_B^2}{S_B}"
        r"=\frac{380^2}{1000}"
        r"=144{,}4\,\Omega"
    )

    st.markdown(TXT_Abt[lang]["Abt_Exp_Text4"])

    st.latex(r"P_i=500\,\mathrm{MW}")
    st.latex(r"P_j=300\,\mathrm{MW}")
    st.latex(r"P_k=-800\,\mathrm{MW}")

    st.markdown(TXT_Abt[lang]["Abt_Exp_Text5"])

    st.latex(
        r"P_i+P_j+P_k=500+300-800=0\,\mathrm{MW}"
    )

    st.markdown(TXT_Abt[lang]["Abt_Exp_Text6"])

    st.latex(r"X_{ij}=28{,}88\,\Omega")
    st.latex(r"X_{ik}=36{,}10\,\Omega")
    st.latex(r"X_{jk}=28{,}88\,\Omega")

    st.markdown(TXT_Abt[lang]["Abt_Exp_Text7"])

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

    st.markdown(TXT_Abt[lang]["Abt_Exp_Sub2"])

    st.markdown(TXT_Abt[lang]["Abt_Exp_Text8"])

    st.latex(r"\theta_k=0")

    st.markdown(TXT_Abt[lang]["Abt_Exp_Text9"])

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

    st.markdown(TXT_Abt[lang]["Abt_Exp_Text10"])

    st.markdown(TXT_Abt[lang]["Abt_Exp_Text11"])

    st.latex(
        r"\theta_i=0{,}10\,\mathrm{rad}=5{,}73^\circ"
    )

    st.latex(
        r"\theta_j=0{,}08\,\mathrm{rad}=4{,}58^\circ"
    )

    st.latex(r"\theta_k=0")

    st.divider()

    st.markdown(TXT_Abt[lang]["Abt_Exp_Sub3"])

    st.markdown(TXT_Abt[lang]["Abt_Exp_Text12"])

    st.markdown(TXT_Abt[lang]["Abt_Exp_Text13"])

    st.latex(
        r"P_{ij}"
        r"=\frac{\theta_i-\theta_j}{x_{ij}}"
        r"=\frac{0{,}10-0{,}08}{0{,}20}"
        r"=0{,}10\,pu"
        r"=100\,\mathrm{MW}"
    )

    st.markdown(TXT_Abt[lang]["Abt_Exp_Text14"])

    st.latex(
        r"P_{ik}"
        r"=\frac{\theta_i-\theta_k}{x_{ik}}"
        r"=\frac{0{,}10-0}{0{,}25}"
        r"=0{,}40\,pu"
        r"=400\,\mathrm{MW}"
    )

    st.markdown(TXT_Abt[lang]["Abt_Exp_Text15"])

    st.latex(
        r"P_{jk}"
        r"=\frac{\theta_j-\theta_k}{x_{jk}}"
        r"=\frac{0{,}08-0}{0{,}20}"
        r"=0{,}40\,pu"
        r"=400\,\mathrm{MW}"
    )

    st.markdown(TXT_Abt[lang]["Abt_Exp_Text16"])

    st.success(TXT_Abt[lang]["Abt_Exp_Success"])

st.divider()

st.divider()

st.success(TXT_Abt[lang]["Abt_End_Success"])

col1, col2 = st.columns(2)

with col1:
    st.page_link(
        "pages/1_Tutorial.py",
        label=TXT_Abt[lang]["Abt_Link_Tut"],
        icon="📘",
    )

with col2:
    st.page_link(
        "app.py",
        label=TXT_Abt[lang]["Abt_Link_Sim"],
        icon="🎮",
    )