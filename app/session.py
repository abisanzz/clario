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
                "section_reads", "line_versions", "delete_pending", "line_filter", "unsaved_lines", "leave_to")


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


# --- Checklist changes that have not been saved yet ---


def unsaved_summary() -> None:
    """What has not been saved, grouped by checklist section: each line and what changed on it."""
    by_section: dict[str, list[dict]] = {}
    for change in st.session_state.get("unsaved_lines", {}).values():
        by_section.setdefault(change["section"], []).append(change)
    for section, changes in sorted(by_section.items()):
        st.markdown(f"**{section}**\n" + "\n".join(f"- {c['line']}: {c['what']}" for c in changes))


def discard_unsaved() -> None:
    """Forget the unsaved changes: each line shows its saved status, tick and comment again."""
    versions = st.session_state.setdefault("line_versions", {})
    for check_id, change in st.session_state.pop("unsaved_lines", {}).items():
        for widget in change["values"]:
            st.session_state.pop(widget, None)
        versions[check_id] = versions.get(check_id, 0) + 1  # fresh fields with the saved values
    st.session_state.pop("leave_to", None)
