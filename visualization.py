from __future__ import annotations

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from texts import TXT_Vis 

TYP_COLORS = {
    "Wind": "#1f77b4",
    "PV": "#ff7f0e",
    "BESS": "#2ca02c",
    "Konventionell": "#7f7f7f",
    "Import/Export": "#9467bd",
    "Lastabwurf": "#8c564b",
    "Verbraucher": "#d62728",
}

TYP_SYMBOLS = {
    "Wind": "triangle-up",
    "PV": "square",
    "BESS": "diamond",
    "Konventionell": "circle",
    "Import/Export": "x",
    "Lastabwurf": "cross",
    "Verbraucher": "star",
}

MARKER_OFFSET_DIRECTIONS = {
    "Wind": (-1.0, 1.0),
    "PV": (1.0, 1.0),
    "BESS": (1.0, -1.0),
    "Konventionell": (-1.0, -1.0),
}


def apply_marker_offsets(
    df: pd.DataFrame,
    lon_col: str = "lon",
    lat_col: str = "lat",
    typ_col: str = "Typ",
    bus_col: str = "Bus",
    offset_deg: float = 0.18,
    intra_type_spread_deg: float = 0.035,
) -> pd.DataFrame:
    out = df.copy()
    if out.empty:
        out["plot_lon"] = []
        out["plot_lat"] = []
        return out

    out["plot_lon"] = pd.to_numeric(out[lon_col], errors="coerce").astype(float)
    out["plot_lat"] = pd.to_numeric(out[lat_col], errors="coerce").astype(float)

    for typ, (dx, dy) in MARKER_OFFSET_DIRECTIONS.items():
        mask = out[typ_col] == typ
        if not bool(mask.any()):
            continue
        lat_rad = np.deg2rad(out.loc[mask, lat_col].astype(float))
        lon_scale = np.maximum(np.cos(lat_rad), 0.35)
        out.loc[mask, "plot_lon"] = out.loc[mask, lon_col].astype(float) + dx * offset_deg / lon_scale
        out.loc[mask, "plot_lat"] = out.loc[mask, lat_col].astype(float) + dy * offset_deg

    if bus_col in out.columns:
        for _, idx in out.groupby([bus_col, typ_col], sort=False).groups.items():
            idx = list(idx)
            if len(idx) <= 1:
                continue
            angles = np.linspace(0.0, 2.0 * np.pi, len(idx), endpoint=False)
            lat_rad = np.deg2rad(out.loc[idx, lat_col].astype(float))
            lon_scale = np.maximum(np.cos(lat_rad), 0.35)
            out.loc[idx, "plot_lon"] = out.loc[idx, "plot_lon"].to_numpy() + intra_type_spread_deg * np.cos(angles) / lon_scale
            out.loc[idx, "plot_lat"] = out.loc[idx, "plot_lat"].to_numpy() + intra_type_spread_deg * np.sin(angles)

    return out


def build_map(
    generators: pd.DataFrame,
    consumers: pd.DataFrame,
    lines: pd.DataFrame,
    hour_row: pd.Series,
    wind_scale: float,
    pv_scale: float,
    konv_scale: float,
    bess_scale: float,
    refs: dict[str, float],
) -> go.Figure:
    lang = st.session_state.get("lang", "DE")
    fig = go.Figure()

    if not lines.empty:
        for _, ln in lines.iterrows():
            util_pct = float(ln.get("Auslastung_pct", 0.0))
            util = util_pct / 100.0
            flow_dc = float(ln.get("Flow_DC_GW", ln.get("Flow_Proxy_GW", 0.0)))
            overloaded = bool(ln.get("Ueberlast", False))
            color = "red" if overloaded else ("orange" if util_pct >= 90 else "green")
            # Mittelpunkt berechnen
            lon_mid = (ln["lon0"] + ln["lon1"]) / 2
            lat_mid = (ln["lat0"] + ln["lat1"]) / 2
            
            # Hover-Text zusammenstellen
            status_txt = TXT_Vis[lang]["Vis_Overload"] if overloaded else TXT_Vis[lang]["Vis_OK"]
            hover_html = (
                f"{ln['Name']} ({ln['von']} → {ln['nach']})<br>"
                f"{TXT_Vis[lang]['Vis_Cap']}: {float(ln['Kapazitaet_GW']):.2f} GW<br>"
                f"{TXT_Vis[lang]['Vis_Flow']}: {flow_dc:+.2f} GW<br>"
                f"{TXT_Vis[lang]['Vis_Util']}: {util_pct:.0f} %<br>"
                f"{TXT_Vis[lang]['Vis_Status']}: {status_txt}"
            )

            # Den unsichtbaren Hover-Punkt in der Mitte hinzufügen
            fig.add_trace(go.Scattergeo(
                lon=[lon_mid],
                lat=[lat_mid],
                mode="markers",
                marker=dict(size=10, opacity=0), # Unsichtbar, aber als Hitbox vorhanden
                text=hover_html,
                hoverinfo="text",
                showlegend=False,
            ))
            # Sichtbare Lines zeichnen
            fig.add_trace(go.Scattergeo(
                lon=[ln["lon0"], ln["lon1"]],
                lat=[ln["lat0"], ln["lat1"]],
                mode="lines",
                line=dict(width=2 + 4 * min(util, 1.5), color=color),
                opacity=0.78,
                hoverinfo="none",
                showlegend=False,
                selected=dict(marker=dict(opacity=1.0)),
                unselected=dict(marker=dict(opacity=1.0))
            ))

    typ_to_value = {
        "Wind": float(hour_row.get("Wind_GW", 0.0)),
        "PV": float(hour_row.get("PV_GW", 0.0)),
        "BESS": float(hour_row.get("BESS_GW", 0.0)),
        "Konventionell": float(hour_row.get("Konv_GW", 0.0)),
    }
    typ_to_inst = {
        "Wind": refs["wind_gw"] * wind_scale,
        "PV": refs["pv_gw"] * pv_scale,
        "BESS": refs["bess_gw"] * bess_scale,
        "Konventionell": refs["konv_gw"] * konv_scale,
    }

    for typ in ["Wind", "PV", "BESS", "Konventionell"]:
        sub = generators[generators["Typ"] == typ].copy()
        if sub.empty:
            continue
            
        if typ == "Wind":
            effective_wind_ratio = st.session_state.get("effective_wind_ratio", 1.0)
            base_wind = typ_to_value["Wind"] / effective_wind_ratio if effective_wind_ratio > 0.01 else 0.0
            
            # WICHTIG: Den reinen globalen Sliderwert zurückrechnen, damit die Tooltips
            # nicht vom Durchschnitt der anderen Slider verfälscht werden!
            wind_scale_global = wind_scale / effective_wind_ratio if effective_wind_ratio > 0.01 else 0.0
            
            sub["Aktuell_GW"] = 0.0
            sub["Installiert_GW"] = 0.0  # Hier weisen wir es separat für Wind zu!
            for idx, row in sub.iterrows():
                share = float(row.get("Anteil", 0.0))
                bus = str(row.get("Bus", ""))
                try:
                    k_num = int(bus.replace("DE0 ", "").strip())
                    faktor = st.session_state.get(f"wind_node_{k_num}", 100) / 100.0
                except ValueError:
                    faktor = 1.0
                
                # Individuellen Slider-Faktor (faktor) anwenden
                sub.at[idx, "Aktuell_GW"] = share * base_wind * faktor
                sub.at[idx, "Installiert_GW"] = share * refs["wind_gw"] * wind_scale_global
                
        elif typ == "Konventionell":
            extra_konv = float(hour_row.get("Extra_Konv_GW", 0.0))
            base_konv = max(typ_to_value["Konventionell"] - extra_konv, 0.0)
            
            sub["Aktuell_GW"] = sub["Anteil"] * base_konv
            
            # Das Zusatzkraftwerk auch auf der Landkarte befeuern!
            sub.loc[sub["Name"] == "backup_DE0 1", "Aktuell_GW"] += extra_konv
            
            # Für Konventionell nutzen wir die Standardberechnung
            sub["Installiert_GW"] = sub["Anteil"] * typ_to_inst[typ]
            
        else:
            # Normalfall (PV, BESS)
            sub["Aktuell_GW"] = sub["Anteil"] * typ_to_value[typ]
            # Standardberechnung
            sub["Installiert_GW"] = sub["Anteil"] * typ_to_inst[typ]
            
        sub = apply_marker_offsets(sub)
        marker_size = 10 + np.sqrt(np.maximum(np.abs(sub["Aktuell_GW"]), 0.0)) * 4.0
        
        # Hover-Text für Knotenpunkte
        hover_texts = [
            f"<b>{n}</b><br>{TXT_Vis[lang]['Vis_Bus']}: {bus}<br>{TXT_Vis[lang]['Vis_Type']}: {typ}<br>"
            f"{TXT_Vis[lang]['Vis_Current']}: {a:.2f} GW<br>{TXT_Vis[lang]['Vis_Ref']}: {i:.2f} GW<br>"
            f"{TXT_Vis[lang]['Vis_OrigPos']}: {lat:.3f}, {lon:.3f}"
            for n, bus, a, i, lat, lon in zip(
                sub["Name"], sub["Bus"], sub["Aktuell_GW"], sub["Installiert_GW"], sub["lat"], sub["lon"]
            )
        ]
        
        fig.add_trace(go.Scattergeo(
            lon=sub["plot_lon"],
            lat=sub["plot_lat"],
            text=hover_texts,
            hoverinfo="text",
            mode="markers",
            name=typ,
            marker=dict(
                size=marker_size,
                color=TYP_COLORS[typ],
                symbol=TYP_SYMBOLS[typ],
                line=dict(width=1, color="black"),
                opacity=0.9,
            ),
            selected=dict(marker=dict(opacity=1.0)),
            unselected=dict(marker=dict(opacity=1.0))
        ))

    if not consumers.empty:
        cluster_load = consumers["Anteil"] * float(hour_row.get("Last_GW", 0.0))
        consumer_texts = [f"<b>{c}</b><br>{TXT_Vis[lang]['Vis_LoadCurrent']}: {l:.2f} GW" for c, l in zip(consumers["Cluster"], cluster_load)]
        
        fig.add_trace(go.Scattergeo(
            lon=consumers["lon"],
            lat=consumers["lat"],
            text=consumer_texts,
            hoverinfo="text",
            mode="markers+text",
            name=TXT_Vis[lang]["Vis_ConsumerCluster"],
            textposition="top center",
            textfont=dict(size=11, color="black"),
            marker=dict(
                size=14 + np.sqrt(np.maximum(cluster_load, 0.0)) * 5.0,
                color=TYP_COLORS["Verbraucher"],
                symbol=TYP_SYMBOLS["Verbraucher"],
                line=dict(width=1.2, color="black"),
                opacity=0.9,
            ),
            selected=dict(
                marker=dict(opacity=0.9), 
                textfont=dict(color="black")
            ),
            unselected=dict(
                marker=dict(opacity=0.9), 
                textfont=dict(color="black")
            )
        ))

    fig.update_geos(
        visible=True,
        resolution=50,
        scope="europe",
        showcountries=True,
        countrycolor="black",
        showland=True,
        landcolor="rgb(240,240,235)",
        showocean=True,
        oceancolor="rgb(220,235,245)",
        lataxis_range=[47.0, 55.8],
        lonaxis_range=[5.0, 16.2],
    )
    fig.update_layout(
        height=620,
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=-0.05, x=0.5, xanchor="center"),
    )
    return fig


def build_stack(df: pd.DataFrame, highlight_hour: int) -> go.Figure:
    lang = st.session_state.get("lang", "DE")
    h = df["Stunde"]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=h, y=df["Konv_GW"], name=TXT_Vis[lang]["Vis_Conv"], marker_color=TYP_COLORS["Konventionell"]))
    fig.add_trace(go.Bar(x=h, y=df["Wind_GW"], name=TXT_Vis[lang]["Vis_Wind"], marker_color=TYP_COLORS["Wind"]))
    fig.add_trace(go.Bar(x=h, y=df["PV_GW"], name=TXT_Vis[lang]["Vis_PV"], marker_color=TYP_COLORS["PV"]))
    fig.add_trace(go.Bar(x=h, y=df["BESS_Entladen_GW"], name=TXT_Vis[lang]["Vis_BESS_Discharge"], marker_color=TYP_COLORS["BESS"]))
    fig.add_trace(go.Bar(x=h, y=-df["BESS_Laden_GW"], name=TXT_Vis[lang]["Vis_BESS_Charge"], marker_color="rgba(44,160,44,0.5)"))
    fig.add_trace(go.Bar(x=h, y=-df["Curtailment_GW"], name=TXT_Vis[lang]["Vis_Curtailment"], marker_color="rgba(214,39,40,0.4)"))
    fig.add_trace(go.Scatter(x=h, y=df["Last_GW"], name=TXT_Vis[lang]["Vis_LoadTarget"], line=dict(color="black", width=3)))
    
    fig.add_vline(x=highlight_hour, line_dash="dash", line_color="red")
    fig.update_layout(
        barmode="relative",
        title=TXT_Vis[lang]["Vis_EnergyMix"],
        xaxis_title=TXT_Vis[lang]["Vis_Hour"],
        yaxis_title=TXT_Vis[lang]["Vis_Power"],
        height=440,
        hovermode="x unified",
    )
    return fig


def build_balance_chart(df: pd.DataFrame, highlight_hour: int) -> go.Figure:
    lang = st.session_state.get("lang", "DE")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df["Stunde"], y=df["Bilanz_vor_BESS_GW"], name=TXT_Vis[lang]["Vis_Bal_PreBESS"]))
    fig.add_trace(go.Scatter(x=df["Stunde"], y=df["Netzbilanz_GW"], name=TXT_Vis[lang]["Vis_Bal_PostBESS"], line=dict(width=3)))
    fig.add_hline(y=0, line_color="black", line_width=1)
    fig.add_hline(y=1, line_dash="dash", line_color="red")
    fig.add_hline(y=-1, line_dash="dash", line_color="red")
    fig.add_vline(x=highlight_hour, line_dash="dash", line_color="red")
    fig.update_layout(
        title=TXT_Vis[lang]["Vis_Bal_Title"],
        xaxis_title=TXT_Vis[lang]["Vis_Hour"],
        yaxis_title="GW",
        height=340,
        hovermode="x unified",
    )
    return fig


def build_line_utilization_chart(line_status: pd.DataFrame) -> go.Figure:
    lang = st.session_state.get("lang", "DE")
    fig = go.Figure()
    if line_status.empty or "Auslastung_pct" not in line_status.columns:
        fig.update_layout(title=TXT_Vis[lang]["Vis_NoLineData"], height=320)
        return fig

    sorted_lines = line_status.sort_values("Auslastung_pct", ascending=False)
    
    hover_texts = [
        f"{row['Name']}<br>{row['von']} → {row['nach']}<br>"
        f"{TXT_Vis[lang]['Vis_Cap']}: {row['Kapazitaet_GW']:.2f} GW<br>"
        f"{TXT_Vis[lang]['Vis_Flow']}: {row.get('Flow_DC_GW', row.get('Flow_Proxy_GW', 0.0)):+.2f} GW<br>"
        f"{TXT_Vis[lang]['Vis_Util']}: {row['Auslastung_pct']:.0f} %"
        for _, row in sorted_lines.iterrows()
    ]
    
    fig.add_trace(go.Bar(
        x=sorted_lines["Name"],
        y=sorted_lines["Auslastung_pct"],
        name=TXT_Vis[lang]["Vis_Util"],
        marker_color=["red" if bool(x) else ("orange" if y >= 90 else "green") for x, y in zip(sorted_lines["Ueberlast"], sorted_lines["Auslastung_pct"])],
        hovertext=hover_texts,
        hoverinfo="text",
    ))
    fig.add_hline(y=100, line_dash="dash", line_color="red")
    fig.update_layout(
        title=TXT_Vis[lang]["Vis_LineUtil_Title"],
        xaxis_title=TXT_Vis[lang]["Vis_Line"],
        yaxis_title=TXT_Vis[lang]["Vis_Util_Pct"],
        height=380,
        margin=dict(l=40, r=20, t=50, b=120),
    )
    fig.update_xaxes(tickangle=-35)
    return fig

def build_line_utilization_chart_24h(line_status_24h: dict[int, pd.DataFrame]) -> go.Figure:
    lang = st.session_state.get("lang", "DE")
    fig = go.Figure()
    
    # Safety-Check
    if not line_status_24h:
        fig.update_layout(title=TXT_Vis[lang]["Vis_NoLineData"], height=320)
        return fig
    
    max_lines_per_hour = []
    
    for hour, df in line_status_24h.items():
        if df.empty or "Auslastung_pct" not in df.columns:
            continue
    
        max_idx = df["Auslastung_pct"].idxmax()
        worst_line_row = df.loc[max_idx].copy()
        worst_line_row["Stunde"] = hour #eventuell doppellung
        max_lines_per_hour.append(worst_line_row)
    
    if not max_lines_per_hour:
        fig.update_layout(title=TXT_Vis[lang]["Vis_NoUtilData"], height=320)
        return fig
    
    summary_df = pd.DataFrame(max_lines_per_hour)
    summary_df = summary_df.sort_values("Stunde") #nur zur Sicherheit
    
    hover_texts = [
        f"{row['Name']}<br>{row['von']} → {row['nach']}<br>"
        f"{TXT_Vis[lang]['Vis_Cap']}: {row['Kapazitaet_GW']:.2f} GW<br>"
        f"{TXT_Vis[lang]['Vis_Flow']}: {row.get('Flow_DC_GW', row.get('Flow_Proxy_GW', 0.0)):+.2f} GW<br>"
        f"{TXT_Vis[lang]['Vis_Util']}: {row['Auslastung_pct']:.0f} %"
        for _, row in summary_df.iterrows()
    ]
    
    fig.add_trace(go.Bar(
        x=summary_df["Stunde"],
        y=summary_df["Auslastung_pct"],
        name=TXT_Vis[lang]["Vis_MaxUtil_Name"],
        marker_color=["red" if bool(x) else ("orange" if y >= 90 else "green") for x, y in zip(summary_df["Ueberlast"], summary_df["Auslastung_pct"])],
        hovertext=hover_texts,
        hoverinfo="text",
    ))
    fig.add_hline(y=100, line_dash="dash", line_color="red")
    fig.update_layout(
        title=TXT_Vis[lang]["Vis_MaxUtil_Title"],
        xaxis_title=TXT_Vis[lang]["Vis_Hour"],
        yaxis_title=TXT_Vis[lang]["Vis_Util_Pct"],
        height=380,
        margin=dict(l=40, r=20, t=50, b=120),
        xaxis=dict(tickmode='linear', tick0=0, dtick=1)
    )
    return fig