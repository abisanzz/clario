"""Starting and opening KYC assessments, shared by the pages. Keeps everything a review needs in the session."""

import streamlit as st

from services.cases import load_case, load_progress, load_supporting

# Made-up team members for the demo sign-in: no passwords, no real accounts
TEAM = {
    "Abi San": "KYC Team Lead",
    "Priya Shah": "KYC Analyst",
    "Tom Okafor": "Senior KYC Analyst",
    "Hannah Ellis": "Senior Manager, Compliance",
}
ASSESSMENT_PAGE = "app_pages/review.py"
ASSESSMENTS_PAGE = "app_pages/assessments.py"
WIDGET_PREFIXES = ("entity_name_", "company_link_", "website_", "fca_", "country_", "registration_", "stated_industry_",
                   "owner", "source")
REVIEW_STATE = ("identification", "labels", "label_comments", "industry", "choice", "assessment", "pack_key", "risk",
                "section_reads", "line_versions", "delete_pending", "line_filter")


def start_over(entity: dict, case_id: str | None) -> None:
    """Load an assessment (or nothing, for a new one): forget the fields' contents and any earlier results."""
    for key in [k for k in st.session_state if str(k).startswith(WIDGET_PREFIXES)]:
        del st.session_state[key]
    for key in REVIEW_STATE:
        st.session_state.pop(key, None)
    st.session_state.entity, st.session_state.case_id = entity, case_id
    st.session_state.switch_tab = "Details & documents"


def open_assessment(case_id: str) -> None:
    """Load a saved assessment, with its label corrections, comments and industry choice."""
    details, stored = load_case(case_id)
    start_over({**details, "documents": stored,
                "supporting": [document for document, _ in load_supporting(case_id)]}, case_id)
    progress = load_progress(case_id)
    if progress:
        st.session_state.update(labels=progress["labels"], pack_key=progress["pack_key"],
                                label_comments=progress.get("comments", {}))
        if progress["choice"]:
            st.session_state.choice = progress["choice"]


def new_assessment() -> None:
    start_over({}, None)
