import streamlit as st

st.set_page_config(page_title="Tutorial", layout="wide")

st.title("Tutorial: Grundlagen der Netzbalance ")
st.write("Willkommen im Tutorial! Hier lernst du Schritt für Schritt, wie du das Netz stabil hältst.")

# --- Put your tutorial content and simplified sliders here ---
st.info("Schritt 1: Passe die Last an...")


# --- Button to return to the main app ---
st.divider()
st.success("Tutorial abgeschlossen? Kehre zum Hauptsimulator zurück.")
st.page_link("app.py", label="Zurück zum Simulator")
