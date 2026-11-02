"""Dashboard: the control centre. KYC operations at a glance: what is active, what needs attention, and recent activity.

Every figure is worked out from the saved assessments and their audit logs.
"""

import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))  # so "services" and "app" can be imported when Streamlit runs this file

from app.session import ASSESSMENT_PAGE, ASSESSMENTS_PAGE, TEAM, new_assessment, open_assessment  # noqa: E402
from services.wording import product_voice  # noqa: E402
from services.overview import (  # noqa: E402
    AI_PROCESSING,
    ANALYST_ACTION,
    CREATION,
    DOCUMENT_UPLOAD,
    all_assessments,
    earlier_approved_reviews,
    recent_activity,
)
from services.workflow import (  # noqa: E402
    STATUSES,
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


def open_case(case_id: str, tab: str | None = None) -> None:
    open_assessment(case_id)
    if tab:
        st.session_state.switch_tab = tab
    st.switch_page(ASSESSMENT_PAGE)


# --- Header ---

with st.container(horizontal=True, vertical_alignment="center"):
    with st.container(width="stretch"):
        hour = datetime.now().hour
        greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
        name = st.session_state.get("user") or st.session_state.get("last_reviewer") or "Analyst"
        st.title(f"{greeting}, {name.split()[0]}")
        st.caption("KYC team operations at a glance: every assessment across the team.")
    with st.container(horizontal=True, width="content", horizontal_alignment="right"):
        if st.button("View all assessments", icon=":material/list:"):
            st.switch_page(ASSESSMENTS_PAGE)
        if st.button("New assessment", type="primary", icon=":material/add:"):
            new_assessment()
            st.switch_page(ASSESSMENT_PAGE)

# Every assessment as it is now, plus earlier approved reviews that a periodic review has since followed
everything = all_assessments() + earlier_approved_reviews()

# --- Filters: by owner (whoever created the assessment) and by status ---

EVERYONE = "Everyone"
owners = list(TEAM) + sorted({a.owner for a in everything} - set(TEAM))  # the team, then anyone else
owner_side, status_side = st.columns([1, 3])  # lines up with the tiles below
owner = owner_side.selectbox("Owner", [EVERYONE] + owners, key="dashboard_owner",
                             help="Whoever created the assessment owns it.")
statuses = status_side.multiselect("Status", STATUSES, key="dashboard_statuses", placeholder="Any status",
                                   help="Show only assessments with these statuses.")
assessments = [a for a in everything if owner == EVERYONE or a.owner == owner]
active = [a for a in assessments if a.active]
cards = {
    "Active assessments": (":material/folder_open:", active,
                           "Being worked on or in review"),
    "Needs attention": (":material/priority_high:", [a for a in assessments if a.needs_attention],
                        "Waiting on someone, due, or high risk"),
    "Pending approval": (":material/approval:", [a for a in assessments if a.status == PENDING_APPROVAL],
                         "Awaiting formal sign-off"),
    "On hold": (":material/pause_circle:", [a for a in assessments if a.status == ON_HOLD],
                "Paused"),
}

# --- Summary cards: click View to filter the work queue ---


def show_card(title: str) -> None:
    st.session_state.dashboard_filter = title
    st.session_state.dashboard_statuses = []  # a card shows its own group of statuses


chosen = st.session_state.get("dashboard_filter", "Active assessments")
selected_card = chosen if not statuses else None
with st.container(horizontal=True, wrap=True):
    for title, (icon, rows, explanation) in cards.items():
        # Every tile the same size, with its View button along the bottom: 4 in a row when wide, 2 by 2 when narrow
        with st.container(border=True, width=228, height=188, vertical_alignment="distribute"):
            with st.container(gap=None):
                st.caption(f"{icon} {title}")
                st.header(str(len(rows)), anchor=False)
                st.caption(explanation)
            selected = title == selected_card
            st.button("Showing" if selected else "View", key=f"card_{title}", type="tertiary",
                      icon=":material/check:" if selected else ":material/arrow_forward:", disabled=selected,
                      on_click=show_card, args=(title,))

# --- Priority work queue ---

DEFAULT_CARD = "Active assessments"


def clear_filters() -> None:
    """Back to the default view: every active assessment, whoever owns it."""
    st.session_state.dashboard_filter = DEFAULT_CARD
    st.session_state.dashboard_statuses = []
    st.session_state.dashboard_owner = EVERYONE


shown = [a for a in assessments if a.status in statuses] if statuses else cards.get(chosen, cards[DEFAULT_CARD])[1]
showing = ", ".join(statuses) if statuses else chosen.lower()
if owner != EVERYONE:
    showing += f" · owned by {owner}"
queue = sorted(shown, key=lambda a: (PRIORITY.get(a.status, 9), a.risk != "High", a.saved_at))
with st.container(border=True):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.subheader(f":material/format_list_bulleted: Priority work queue: {showing}", width="stretch")
        if chosen != DEFAULT_CARD or statuses or owner != EVERYONE:  # hidden on the default view
            st.button("Clear filters", icon=":material/filter_alt_off:", key="clear_filters", on_click=clear_filters,
                      help="Back to all active assessments, for everyone.")
    if not everything:
        st.info("No assessments yet. Click **New assessment** to start one.", icon=":material/info:")
    elif not queue:
        st.caption(f"Nothing to show for {showing}.")
    else:
        widths = [3.6, 3, 3.6, 1.2]
        for column, heading in zip(st.columns(widths), ["Legal entity · Assessment ID · Owner",
                                                         "Risk rating · Status", "Next action · Review due"]):
            column.caption(f"**{heading}**")
        for a in queue:
            st.divider()
            entity, badges, action, opener = st.columns(widths, vertical_alignment="center")
            entity.markdown(f"**{a.entity_name}**")
            entity.caption(f"`{a.review_id}`" + (f" · {a.company}" if a.company else "") + f" · {a.owner}")
            with badges.container(horizontal=True, gap="small"):
                if a.risk:
                    st.badge(f"{a.risk} risk", color=RISK_COLOURS[a.risk])
                else:
                    st.badge("Not rated", color="gray")
                st.badge(a.status, color=STATUS_COLOURS[a.status], help=DEFINITIONS[a.status])
            action.markdown(a.next_action)
            if a.next_review:  # only assessments approved before have a next review date
                action.caption("Review due " + datetime.fromisoformat(a.next_review).strftime("%d %b %Y"))
            if opener.button("Open", key=f"open_{a.review_id}", icon=":material/arrow_forward:", width="stretch"):
                open_case(a.case_id, "Ongoing monitoring" if a.followed_by else None)  # its review history

# --- Recent activity ---

activity = recent_activity(limit=12)
with st.expander(f"Recent activity ({len(activity)})", icon=":material/history:"):  # closed until opened
    st.caption(
        ":material/help: The 12 most recent actions across the whole team's assessments, newest first, taken from "
        "each assessment's audit history: new assessments, document uploads, Clario's AI processing (identifying "
        "documents, rating risk, running the checks) and analyst actions (validating lines, approvals, status and "
        "owner changes). For an assessment's full record, open its **Audit history** tab."
    )
    if not activity:
        st.caption("No activity yet. Document uploads, AI processing, new assessments and analyst actions appear "
                   "here.")
    for event in activity:
        when = datetime.strptime(event.at, "%Y-%m-%d %H:%M:%S").strftime("%d %b, %H:%M")
        icon_side, text_side = st.columns([0.4, 9.6], vertical_alignment="top")
        icon_side.markdown(ACTIVITY_ICONS[event.kind])
        text_side.markdown(product_voice(event.what) + (f" · line {event.line}" if event.line else ""))
        text_side.caption(f"{event.entity_name} · `{event.review_id}` · {product_voice(event.who)} · {when} · "
                          f"{event.kind}")
