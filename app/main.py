"""Clario: dashboard, case list, assessments and the About page, with the menu in a navy sidebar.

Run from the project folder:  .venv/bin/streamlit run app/main.py
"""

from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).resolve().parent.parent / "assets"

st.set_page_config(page_title="Clario", page_icon=str(ASSETS / "clario-icon.svg"), layout="wide")
st.logo(str(ASSETS / "clario-logo.svg"), icon_image=str(ASSETS / "clario-icon.svg"), size="large")

dashboard = st.Page("app_pages/dashboard.py", title="Dashboard", icon=":material/space_dashboard:", default=True)
assessments = st.Page("app_pages/assessments.py", title="KYC Assessments", icon=":material/folder_shared:",
                      url_path="assessments")
assessment = st.Page("app_pages/review.py", title="Assessment", icon=":material/fact_check:", url_path="assessment",
                     visibility="hidden")  # opened from the case list or the dashboard
about = st.Page("app_pages/home.py", title="About Clario", icon=":material/info:", url_path="about")
page = st.navigation([dashboard, assessments, assessment, about], position="sidebar")
st.sidebar.caption("KYC document review for UK financial services")
page.run()
