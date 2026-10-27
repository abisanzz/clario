"""Clario: the landing page and the document review page, with a menu at the top.

Run from the project folder:  .venv/bin/streamlit run app/main.py
"""

import streamlit as st

st.set_page_config(page_title="Clario", page_icon=":material/fact_check:", layout="wide")

home = st.Page("app_pages/home.py", title="Home", icon=":material/home:", default=True)
review = st.Page("app_pages/review.py", title="Review", icon=":material/fact_check:", url_path="review")
st.navigation([home, review], position="top").run()
