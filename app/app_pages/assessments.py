"""KYC Assessments: every legal entity being reviewed, with its progress. Start a new assessment or open one."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))  # so "services" and "app" can be imported when Streamlit runs this file

from app.session import ASSESSMENT_PAGE, new_assessment, open_assessment, status_guide  # noqa: E402
from services.overview import all_assessments  # noqa: E402

st.title("Assessments")
st.caption("Search, open or start a KYC assessment.")
# A little less margin either side on this page, so every column of the table fits on screen
st.html("""<style>
[data-testid="stMainBlockContainer"] { padding-left: 2.5rem; padding-right: 2.5rem; }
</style>""")

RECENT = 10  # shown when the page opens; search finds the rest
assessments = sorted(all_assessments(), key=lambda a: a.last_activity, reverse=True)  # most recent first


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
    if st.button("New assessment", icon=":material/add:"):
        new_assessment()
        st.switch_page(ASSESSMENT_PAGE)
    with st.popover("What the statuses mean", icon=":material/help:"):
        status_guide()

if not assessments:
    st.info("No assessments yet. Click **New assessment** to start one.", icon=":material/info:")
    st.stop()

rows = [found] if found else assessments[:RECENT]
if found:
    st.caption(f"Showing {found.entity_name}. Clear the search to see the most recent assessments.")
elif len(assessments) > RECENT:
    st.caption(f"The {RECENT} most recently worked on of {len(assessments)} assessments. Search to find any other. "
               "Select a row to open it.")
else:
    st.caption(f"{len(assessments)} assessments, most recently worked on first. Select a row to open it.")
picked = st.dataframe(
    pd.DataFrame([{
        "Review ID": a.review_id,
        "Legal entity": a.entity_name,
        "Status": a.status,
        "Checklist": a.checklist or "Not set yet",  # its name gives the industry and risk level
        "Owner": a.owner,
        "Next review": a.next_review,
    } for a in rows]),
    hide_index=True,
    height="content",
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "Review ID": st.column_config.TextColumn(width=150),
        "Legal entity": st.column_config.TextColumn(width=250),
        "Status": st.column_config.TextColumn(
            width=104, help="Where the review has got to. **What the statuses mean**, above the table, explains each one."),
        "Checklist": st.column_config.TextColumn(width=305),  # wide enough for the whole name
        "Owner": st.column_config.TextColumn(width=105),
        "Next review": st.column_config.TextColumn(width=100),
    },
)
# One place to open from, under the table: the entity found by search, or the row selected
chosen = found or (rows[picked.selection.rows[0]] if picked.selection.rows else None)
if chosen:
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown(f"**{chosen.entity_name}** · {chosen.review_id} · {chosen.status}", width="stretch")
        if st.button("Open assessment", type="primary", icon=":material/folder_open:", key="open_chosen"):
            open_case(chosen.case_id)
