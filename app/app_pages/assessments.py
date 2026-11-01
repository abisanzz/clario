"""KYC Assessments: every legal entity being reviewed, with its progress. Start a new assessment or open one."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))  # so "services" and "app" can be imported when Streamlit runs this file

from app.session import ASSESSMENT_PAGE, new_assessment, open_assessment  # noqa: E402
from services.cases import find_by_review_id  # noqa: E402
from services.overview import all_assessments  # noqa: E402

st.title("KYC Assessments")
st.caption("Every legal entity being reviewed. Each entity has one assessment, with its own review ID.")

with st.container(horizontal=True, vertical_alignment="bottom"):
    if st.button("New assessment", type="primary", icon=":material/add:"):
        new_assessment()
        st.switch_page(ASSESSMENT_PAGE)
    typed_id = st.text_input("Find by review ID", placeholder="e.g. CLR-E9BD2CD5", width=260)
    if st.button("Find", icon=":material/search:", disabled=not typed_id.strip()):
        found = find_by_review_id(typed_id)
        if found:
            open_assessment(found)
            st.switch_page(ASSESSMENT_PAGE)
        st.error(f"No assessment has the ID {typed_id.strip().upper()}.", icon=":material/error:")

assessments = all_assessments()
if not assessments:
    st.info("No assessments yet. Click **New assessment** to start one.", icon=":material/info:")
    st.stop()

st.caption("Select a row to open it.")
picked = st.dataframe(
    pd.DataFrame([{
        "Legal entity": a.entity_name,
        "Review ID": a.review_id,
        "Industry": a.industry or "Not confirmed yet",
        "Risk": a.risk or "Not rated yet",
        "Checklist": a.checklist or "Not set yet",
        "Lines validated": a.validated / a.lines if a.lines else 0.0,
        "Status": a.status,
        "Next review": a.next_review,
        "Reason": a.status_reason,
        "Last saved": a.saved_at,
    } for a in assessments]),
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "Lines validated": st.column_config.ProgressColumn(format="percent", min_value=0.0, max_value=1.0,
                                                           help="Checklist lines validated before approval"),
    },
)
if picked.selection.rows:
    chosen = assessments[picked.selection.rows[0]]
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown(f"**{chosen.entity_name}** · {chosen.review_id} · {chosen.status}", width="stretch")
        if st.button("Open assessment", type="primary", icon=":material/folder_open:"):
            open_assessment(chosen.case_id)
            st.switch_page(ASSESSMENT_PAGE)
