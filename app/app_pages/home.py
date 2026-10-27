"""Clario landing page: what the agent does, what to provide, and what you get back."""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))  # so "services" can be imported when Streamlit runs this file

from services.cases import list_cases  # noqa: E402
from services.pack import DOCUMENT_TYPES  # noqa: E402

REVIEW_PAGE = "app_pages/review.py"


def cards(items: list[tuple[str, str, str]]) -> None:
    """A row of bordered cards, each with an icon, a heading and a sentence."""
    with st.container(horizontal=True):
        for icon, heading, text in items:
            with st.container(border=True):
                st.markdown(f"**{icon} {heading}**")
                st.caption(text)


def start_button(key: str) -> None:
    with st.container(horizontal=True):
        if st.button("Start document review", type="primary", icon=":material/arrow_forward:", key=key):
            st.session_state.screen = "details"
            st.switch_page(REVIEW_PAGE)
        if list_cases() and st.button("Continue a saved review", icon=":material/folder_open:", key=f"{key}_continue"):
            st.session_state.screen = "details"  # the saved reviews are listed at the top of the first screen
            st.switch_page(REVIEW_PAGE)


# --- Hero ---

st.title("Clario")
with st.container(horizontal=True, vertical_alignment="center"):
    st.markdown("**KYC Document Review Agent**")
    st.badge("AI-powered", icon=":material/auto_awesome:", color="violet")
st.markdown("## Turn KYC documents into actionable insights.")
st.markdown(
    "Review client documentation, extract relevant information and identify potential gaps, inconsistencies and "
    "items requiring further review, checked against Companies House and the FCA register, all in one place."
)
with st.container(horizontal=True):
    for label, icon in [
        ("Document analysis", ":material/description:"),
        ("Information extraction", ":material/data_object:"),
        ("Gap identification", ":material/rule:"),
        ("Public register checks", ":material/account_balance:"),
    ]:
        st.badge(label, icon=icon, color="gray")
start_button("start_top")

# --- What Clario does ---

st.header("What Clario does")
cards([
    (":material/plagiarism:", "1. Reviews your documents",
     "Identifies each uploaded KYC document and analyses it for information relevant to client due diligence."),
    (":material/table_view:", "2. Extracts key information",
     "Organises entity, ownership, people and business information into a structured, easy-to-review format."),
    (":material/flag:", "3. Highlights potential issues",
     "Flags missing information, inconsistencies between documents, and details that don't match Companies House "
     "or the FCA register."),
    (":material/rate_review:", "4. Supports your review",
     "Gives findings with document and page references, so a reviewer can validate them and decide the next steps."),
    (":material/speed:", "5. Suggests a risk rating",
     "Rates customer, product, geography and delivery channel risk against your methodology, and flags enhanced due "
     "diligence triggers, for the reviewer to confirm."),
])

# --- What you'll get ---

st.header("What you'll get")
cards([
    (":material/fact_check:", "Extracted information", "Key facts identified in the documents and public registers."),
    (":material/report:", "Potential gaps", "Checklist items that appear missing, unclear or inconsistent."),
    (":material/link:", "Evidence references", "The document, page and quote behind each finding."),
    (":material/checklist:", "Recommended follow-ups",
     "What to request from the client and what to check on public registers."),
    (":material/speed:", "Suggested risk rating",
     "Low, Medium or High, with the reasons and evidence for each factor."),
])

# --- Review, verification and decision ---

st.header("Review, verification and decision")
st.caption("Clario does the first, supports the second, and suggests a risk rating for the third. The decision "
           "is always yours.")
cards([
    (":material/smart_toy:", "Document review: what Clario does",
     "Extracts and organises information from the documents supplied, checks it against Companies House and the "
     "FCA register, and identifies potential issues."),
    (":material/verified:", "Verification: what requires evidence",
     "Establishing whether information is supported by reliable evidence and, where necessary, independent sources. "
     "Clario points to the evidence; a reviewer confirms it."),
    (":material/gavel:", "KYC decision: what your firm determines",
     "Confirming the client's risk rating and deciding whether onboarding, further due diligence or escalation is "
     "appropriate. Clario suggests a rating; the reviewer, and senior management for high risk, decide."),
])

# --- More detail ---

left, middle, right = st.columns(3)
with left.container(border=True):
    st.markdown("**:material/groups: Who it's for**")
    st.markdown("KYC analysts, client onboarding teams, compliance professionals and client operations teams.")
with middle.container(border=True):
    st.markdown("**:material/upload_file: What to upload**")
    st.markdown("PDFs or photos (PNG, JPEG, WebP, GIF) of documents such as:")
    st.markdown("\n".join(f"- {label}" for key, label in DOCUMENT_TYPES.items() if key != "other"))
with right.container(border=True):
    st.markdown("**:material/block: What it doesn't do**")
    st.markdown(
        "- It doesn't verify that a document is authentic.\n"
        "- It doesn't run sanctions, PEP or adverse media screening.\n"
        "- It doesn't make the risk decision or approve a client: it suggests a rating for the reviewer to "
        "confirm."
    )

with st.container(border=True):
    st.markdown("**:material/lock: How your information is handled**")
    st.markdown(
        "- Uploaded documents are sent to Anthropic's API so Claude can read them.\n"
        "- Each review (its details, documents and progress) is saved on the computer running Clario when you "
        "click Next or Save as draft, so you can reopen it later to add documents or edit details.\n"
        "- The company number and FCA firm reference number you enter are looked up on the public Companies House "
        "and FCA registers.\n"
        "- A reviewer's changes to results are saved only on the computer running Clario."
    )

st.info(
    "**Designed to support human judgement.** Clario assists with document review; it does not replace compliance "
    "expertise, independent verification or your firm's KYC policies. All findings should be validated by an "
    "appropriate reviewer.",
    icon=":material/person_check:",
)
st.caption(
    "Only upload documents you are authorised to process. Handle client information in accordance with your firm's "
    "data protection and information security requirements."
)
start_button("start_bottom")
