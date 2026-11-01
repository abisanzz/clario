"""Dashboard: the control centre. KYC operations at a glance: what is active, what needs attention, and recent activity.

Every figure is worked out from the saved assessments and their audit logs.
"""

import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))  # so "services" and "app" can be imported when Streamlit runs this file

from app.session import ASSESSMENT_PAGE, ASSESSMENTS_PAGE, new_assessment, open_assessment  # noqa: E402
from services.overview import (  # noqa: E402
    AI_PROCESSING,
    ANALYST_ACTION,
    CREATION,
    DOCUMENT_UPLOAD,
    all_assessments,
    recent_activity,
)
from services.workflow import (  # noqa: E402
    APPROVED,
    CANCELLED,
    DEFINITIONS,
    IN_PROGRESS,
    NOT_STARTED,
    ON_HOLD,
    PENDING_APPROVAL,
    REJECTED,
    UNDER_REVIEW,
)

STATUS_COLOURS = {NOT_STARTED: "gray", IN_PROGRESS: "blue", UNDER_REVIEW: "violet", PENDING_APPROVAL: "orange",
                  APPROVED: "green", REJECTED: "red", ON_HOLD: "orange", CANCELLED: "gray"}
RISK_COLOURS = {"Low": "green", "Medium": "orange", "High": "red"}
ACTIVITY_ICONS = {DOCUMENT_UPLOAD: ":material/upload_file:", AI_PROCESSING: ":material/smart_toy:",
                  CREATION: ":material/add_circle:", ANALYST_ACTION: ":material/person:"}
# Order of the work queue: what is waiting on someone first
PRIORITY = {PENDING_APPROVAL: 0, ON_HOLD: 1, NOT_STARTED: 2, UNDER_REVIEW: 3, IN_PROGRESS: 4}


def open_case(case_id: str) -> None:
    open_assessment(case_id)
    st.switch_page(ASSESSMENT_PAGE)


# --- Header ---

with st.container(horizontal=True, vertical_alignment="center"):
    with st.container(width="stretch"):
        st.title("Dashboard")
        st.caption("Your KYC operations at a glance.")
    with st.container(horizontal=True, width="content", horizontal_alignment="right"):
        if st.button("View all assessments", icon=":material/list:"):
            st.switch_page(ASSESSMENTS_PAGE)
        if st.button("New assessment", type="primary", icon=":material/add:"):
            new_assessment()
            st.switch_page(ASSESSMENT_PAGE)

assessments = all_assessments()
active = [a for a in assessments if a.active]
cards = {
    "Active assessments": (":material/folder_open:", active, "Not yet approved, rejected or cancelled"),
    "Needs attention": (":material/priority_high:", [a for a in assessments if a.needs_attention],
                        "Waiting on someone, due, or high risk"),
    "Pending approval": (":material/approval:", [a for a in assessments if a.status == PENDING_APPROVAL],
                         "Ready for formal sign-off"),
    "On hold": (":material/pause_circle:", [a for a in assessments if a.status == ON_HOLD],
                "Paused until an issue is resolved"),
}

# --- Summary cards: click View to filter the work queue ---

chosen = st.session_state.get("dashboard_filter", "Active assessments")
with st.container(horizontal=True):
    for title, (icon, rows, explanation) in cards.items():
        with st.container(border=True, width=205):  # fixed width: 4 in a row when wide, 2 by 2 when narrow
            st.caption(f"{icon} {title}")
            st.markdown(f"## {len(rows)}")
            st.caption(explanation)
            selected = title == chosen
            if st.button("Showing below" if selected else "View", key=f"card_{title}", type="tertiary",
                         icon=":material/check:" if selected else ":material/arrow_forward:", disabled=selected):
                st.session_state.dashboard_filter = title
                st.rerun()

# --- Priority work queue ---

queue = sorted(cards[chosen][1], key=lambda a: (PRIORITY.get(a.status, 9), a.risk != "High", a.saved_at))
with st.container(border=True):
    st.subheader(f":material/format_list_bulleted: Priority work queue: {chosen.lower()}")
    if not assessments:
        st.info("No assessments yet. Click **New assessment** to start one.", icon=":material/info:")
    elif not queue:
        st.caption(f"Nothing to show for {chosen.lower()}.")
    else:
        widths = [3.6, 3, 3.6, 1.2]
        for column, heading in zip(st.columns(widths), ["Legal entity · Assessment ID", "Risk rating · Status",
                                                         "Next action · Review due"]):
            column.caption(f"**{heading}**")
        for a in queue:
            st.divider()
            entity, badges, action, opener = st.columns(widths, vertical_alignment="center")
            entity.markdown(f"**{a.entity_name}**")
            entity.caption(f"`{a.review_id}`" + (f" · {a.company}" if a.company else ""))
            with badges.container(horizontal=True, gap="small"):
                if a.risk:
                    st.badge(f"{a.risk} risk", color=RISK_COLOURS[a.risk])
                else:
                    st.badge("Not rated", color="gray")
                st.badge(a.status, color=STATUS_COLOURS[a.status], help=DEFINITIONS[a.status])
            action.markdown(a.next_action)
            action.caption("Review due " + datetime.fromisoformat(a.next_review).strftime("%d %b %Y")
                           if a.next_review else "Review due: not set until approved")
            if opener.button("Open", key=f"open_{a.case_id}", icon=":material/arrow_forward:", width="stretch"):
                open_case(a.case_id)

# --- Recent activity ---

with st.container(border=True):
    st.subheader(":material/history: Recent activity")
    activity = recent_activity(limit=12)
    if not activity:
        st.caption("No activity yet. Document uploads, AI processing, new assessments and analyst actions appear "
                   "here.")
    for event in activity:
        when = datetime.strptime(event.at, "%Y-%m-%d %H:%M:%S").strftime("%d %b, %H:%M")
        icon_side, text_side = st.columns([0.4, 9.6], vertical_alignment="top")
        icon_side.markdown(ACTIVITY_ICONS[event.kind])
        text_side.markdown(f"{event.what}" + (f" · line {event.line}" if event.line else ""))
        text_side.caption(f"{event.entity_name} · `{event.review_id}` · {event.who} · {when} · {event.kind}")
