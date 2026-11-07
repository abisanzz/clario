"""Clario: a demo sign-in, then the menu in a navy sidebar with the workspace pages and shortcuts into the open
assessment.

Run from the project folder:  .venv/bin/streamlit run app/main.py
"""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))  # so "app" and "services" can be imported
ASSETS = PROJECT_ROOT / "assets"

from app.session import (  # noqa: E402
    REVIEW_STATE,
    TEAM,
    WIDGET_PREFIXES,
    discard_unsaved,
    new_assessment,
    open_assessment,
    unsaved_summary,
)
from services.cases import list_cases  # noqa: E402

st.set_page_config(page_title="Clario", page_icon=str(ASSETS / "clario-icon.svg"), layout="wide")
st.logo(str(ASSETS / "clario-logo.svg"), icon_image=str(ASSETS / "clario-icon.svg"), size="large")
# Body text and field labels a touch heavier. No colours here: the light and dark themes in .streamlit/config.toml
# set them, so this reads the same in either mode
st.html("""<style>
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li { font-weight: 450; }
[data-testid="stWidgetLabel"] p { font-weight: 500; }
</style>""")


def sign_in() -> None:
    """Choose a team member to continue. A demo: anyone can sign in as anyone."""
    with st.container(horizontal=True, horizontal_alignment="center"), st.container(width=440):
        st.space("large")
        with st.container(border=True):
            st.image(str(ASSETS / "clario-icon.svg"), width=48)
            st.title("Sign in to Clario")
            st.caption("AI KYC document intelligence for the KYC Operations team.")
            user = st.selectbox("Account", list(TEAM), format_func=lambda name: f"{name} · {TEAM[name]}",
                                key="sign_in_account")
            if st.button("Sign in", type="primary", icon=":material/login:", width="stretch"):
                st.session_state.user = user
                st.session_state.last_reviewer = user
                st.session_state.just_signed_in = True  # signing in always opens the Dashboard
                st.rerun()
        st.caption(":material/info: Demo environment: choose a team member to continue. No password is needed.")


def sign_out() -> None:
    for key in [k for k in st.session_state if str(k).startswith(WIDGET_PREFIXES)]:
        del st.session_state[key]
    for key in (*REVIEW_STATE, "user", "last_reviewer", "case_id", "entity", "current_tab", "dashboard_filter",
                "dashboard_owner", "dashboard_statuses"):
        st.session_state.pop(key, None)
    st.query_params.clear()


# Stay signed in, with the same assessment and tab open, when the page is refreshed: the page's address keeps them
remembered_user = st.query_params.get("user")
if "user" not in st.session_state and remembered_user in TEAM:
    st.session_state.user = st.session_state.last_reviewer = remembered_user
    remembered_case = st.query_params.get("case")
    if remembered_case and any(draft["id"] == remembered_case for draft in list_cases()):
        open_assessment(remembered_case)
        if st.query_params.get("tab"):
            st.session_state.switch_tab = st.query_params["tab"]


# Every page's address, so a bookmark or link opened while signed out shows the sign-in, then that page
PAGE_PATHS = ["assessments", "new", "assessment", "document-intelligence", "evidence-review", "audit-history", "about"]

if "user" not in st.session_state:
    st.navigation([st.Page(sign_in, title="Sign in", icon=":material/login:", default=True)]
                  + [st.Page(sign_in, title="Sign in", url_path=path, visibility="hidden") for path in PAGE_PATHS],
                  position="hidden").run()
    st.stop()

assessment = st.Page("app_pages/review.py", title="Assessment", icon=":material/fact_check:", url_path="assessment",
                     visibility="hidden")  # opened from the assessments list, the dashboard or the menu


def start_new_assessment() -> None:
    new_assessment()
    st.switch_page(assessment)


def open_tab(tab: str, icon: str):
    """A menu item that opens this tab of the assessment being worked on, or asks which assessment to open."""

    def page() -> None:
        if st.session_state.get("case_id"):
            st.session_state.switch_tab = tab
            st.switch_page(assessment)
        st.title(tab)
        st.info(f"Open an assessment to see its {tab.lower()}.", icon=icon)
        if st.button("Go to Assessments", type="primary", icon=":material/folder_open:"):
            st.switch_page("app_pages/assessments.py")

    return page


workspace = [
    dashboard := st.Page("app_pages/dashboard.py", title="Dashboard", icon=":material/space_dashboard:", default=True),
    st.Page("app_pages/assessments.py", title="Assessments", icon=":material/folder_open:", url_path="assessments"),
    st.Page(start_new_assessment, title="New assessment", icon=":material/add_circle:", url_path="new"),
    assessment,
]
management = [
    st.Page(open_tab("Document intelligence", ":material/plagiarism:"), title="Document intelligence",
            icon=":material/plagiarism:", url_path="document-intelligence"),
    st.Page(open_tab("Evidence review", ":material/checklist:"), title="Evidence review",
            icon=":material/checklist:", url_path="evidence-review"),
    st.Page(open_tab("Audit history", ":material/history:"), title="Audit history", icon=":material/history:",
            url_path="audit-history"),
]
help_pages = [st.Page("app_pages/home.py", title="About Clario", icon=":material/info:", url_path="about")]
page = st.navigation({"Workspace": workspace, "Management": management, "Help": help_pages}, position="sidebar")

with st.sidebar:
    st.divider()
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.markdown(":material/account_circle:", width="content")
        with st.container(gap=None):
            st.markdown(f"**{st.session_state.user}**")
            st.caption(TEAM.get(st.session_state.user, "KYC Operations"))
    st.button("Sign out", icon=":material/logout:", type="tertiary", on_click=sign_out)


@st.dialog("Unsaved changes", icon=":material/warning:", dismissible=False, width="medium")
def unsaved_elsewhere() -> None:
    """Shown when the menu is used to leave a checklist with changes that have not been saved."""
    tab = next(iter(st.session_state.unsaved_lines.values()))["tab"]
    st.warning(f"You left **{tab}** with checklist changes that have not been saved. Continuing without saving will "
               "lose them.", icon=":material/warning:")
    unsaved_summary()
    back, discard = st.columns(2)
    if back.button(f"Return to {tab}", type="primary", icon=":material/undo:", width="stretch"):
        st.session_state.switch_tab = tab
        st.switch_page(assessment)
    if discard.button("Discard changes", icon=":material/delete:", width="stretch"):
        discard_unsaved()
        st.rerun()


if st.session_state.pop("just_signed_in", False) and page.url_path != dashboard.url_path:
    st.switch_page(dashboard)

if st.session_state.get("unsaved_lines") and page.url_path not in ("assessment", "evidence-review"):
    unsaved_elsewhere()
    st.stop()  # the chosen page opens once the user has decided

st.query_params["user"] = st.session_state.user
for name, value in (("case", st.session_state.get("case_id")), ("tab", st.session_state.get("current_tab"))):
    if value:
        st.query_params[name] = value
    else:
        st.query_params.pop(name, None)
page.run()
