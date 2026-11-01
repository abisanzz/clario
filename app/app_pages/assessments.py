"""KYC Assessments: every legal entity being reviewed, with its progress. Start a new assessment or open one."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))  # so "services" and "app" can be imported when Streamlit runs this file

from app.session import ASSESSMENT_PAGE, new_assessment, open_assessment  # noqa: E402
from services.overview import all_assessments  # noqa: E402

st.title("Assessments")
st.caption("Search, open or start a KYC assessment.")

assessments = all_assessments()


def open_case(case_id: str) -> None:
    open_assessment(case_id)
    st.switch_page(ASSESSMENT_PAGE)


# --- Search: type part of a legal entity name or review ID, and matching assessments are suggested ---

with st.container(horizontal=True, vertical_alignment="bottom"):
    found = st.selectbox(
        "Search", assessments, index=None, key="assessment_search", width=520,
        format_func=lambda a: f"{a.entity_name} · {a.review_id} · {a.status}",
        placeholder="Search by legal entity name or review ID",
        help="Type part of a name or ID, e.g. \"payments\" or \"9580\", and pick a suggestion.",
    )
    if found and st.button("Open assessment", type="primary", icon=":material/folder_open:", key="open_found"):
        open_case(found.case_id)
    if st.button("New assessment", icon=":material/add:"):
        new_assessment()
        st.switch_page(ASSESSMENT_PAGE)

if not assessments:
    st.info("No assessments yet. Click **New assessment** to start one.", icon=":material/info:")
    st.stop()

rows = [found] if found else assessments
st.caption(f"Showing {found.entity_name}. Clear the search to see every assessment." if found
           else f"{len(assessments)} assessments. Select a row to open it.")
picked = st.dataframe(
    pd.DataFrame([{
        "Legal entity": a.entity_name,
        "Review ID": a.review_id,
        "Owner": a.owner,
        "Industry": a.industry or "Not confirmed yet",
        "Risk": a.risk or "Not rated yet",
        "Checklist": a.checklist or "Not set yet",
        "Lines validated": a.validated / a.lines if a.lines else 0.0,
        "Status": a.status,
        "Next review": a.next_review,
        "Reason": a.status_reason,
        "Last saved": a.saved_at,
    } for a in rows]),
    hide_index=True,
    height="content",
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "Lines validated": st.column_config.ProgressColumn(format="percent", min_value=0.0, max_value=1.0,
                                                           help="Checklist lines validated before approval"),
    },
)
if picked.selection.rows and not found:
    chosen = rows[picked.selection.rows[0]]
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown(f"**{chosen.entity_name}** · {chosen.review_id} · {chosen.status}", width="stretch")
        if st.button("Open assessment", type="primary", icon=":material/folder_open:", key="open_selected"):
            open_case(chosen.case_id)
