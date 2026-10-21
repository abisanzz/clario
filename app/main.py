"""Clario KYC workspace: upload a company's documents, add links, and see which checklist items are covered.

Run from the project folder:  .venv/bin/streamlit run app/main.py
"""

import sys
from itertools import groupby
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))  # so "services" can be imported when Streamlit runs this file

from services.companies_house import (  # noqa: E402
    CompanyNotFound,
    LookupFailed,
    get_company,
    nature_of_business,
    parse_company_number,
)
from services.extractor import ExtractionFailed  # noqa: E402
from services.checklist import CHECKLISTS  # noqa: E402
from services.industry import INDUSTRIES, SOURCES_AGREE, checklist_for, suggest_industry  # noqa: E402
from services.pack import (  # noqa: E402
    DOCUMENT_TYPES,
    DocumentLabel,
    LinkedSource,
    UnsupportedFile,
    UploadedDocument,
    assess_pack,
    companies_house_source,
    identify_documents,
    pack_fingerprint,
)
from services.validator import Status  # noqa: E402
from services.website import WebsiteFetchFailed, website_text  # noqa: E402

SAMPLES = PROJECT_ROOT / "sample_documents"
SAMPLE_FILES = [SAMPLES / "certificate_of_incorporation.pdf"] + sorted((SAMPLES / "pack").glob("*.pdf"))
SAMPLE_ANSWERS = {
    "labels": SAMPLES / "pack_labels.answer.json",
    "industry": SAMPLES / "pack_industry.answer.json",
    "assessment": SAMPLES / "pack_assessment.answer.json",
}
SAMPLE_COMPANY_NUMBER = "99999901"
UPLOAD_TYPES = ["pdf", "png", "jpg", "jpeg", "webp", "gif"]

STATUS_TEXT = {
    Status.PRESENT: "✅ Present",
    Status.MISSING: "❌ Missing",
    Status.UNCLEAR: "⚠️ Unclear",
    Status.NEEDS_HUMAN_REVIEW: "🔎 Needs human review",
    Status.NOT_STARTED: "⏳ Not started",
}
TYPE_KEY = {label: key for key, label in DOCUMENT_TYPES.items()}
INDUSTRY_KEY = {label: key for key, label in INDUSTRIES.items()}
CHECKLIST_KEY = {name: key for key, (name, _) in CHECKLISTS.items()}
SAMPLE_CHECKLIST = "fintech"  # the checklist the sample pack's saved answer was made with


@st.cache_data(ttl=3600, max_entries=50, show_spinner="Checking Companies House and the website...")
def fetch_links(company_link: str, website: str) -> tuple[list[LinkedSource], list[str]]:
    """The Companies House record and website text, plus a warning for each link that could not be read."""
    sources, warnings = [], []
    if parse_company_number(company_link):
        try:
            sources.append(companies_house_source(company_link))
        except LookupFailed as error:
            warnings.append(f"Companies House could not be checked ({error}); continuing without it.")
    if website.strip():
        try:
            sources.append(LinkedSource("Company website", website_text(website)))
        except WebsiteFetchFailed as error:
            warnings.append(f"The website could not be read ({error}); continuing without it.")
    return sources, warnings


@st.cache_data(ttl=3600, max_entries=50, show_spinner="Looking up Companies House...")
def industry_codes(company_number: str) -> list[tuple[str, str]] | str:
    """The company's SIC codes with their meanings, or a sentence saying why there are none."""
    try:
        return nature_of_business(get_company(company_number))
    except CompanyNotFound:
        return "This company is not on the Companies House register, so there are no industry codes."
    except LookupFailed as error:
        return f"Companies House could not be checked ({error})."


def show_industry(link_or_number: str) -> None:
    """Show the company's industry codes (SIC codes) from Companies House under the link box."""
    if not link_or_number.strip():
        return
    number = parse_company_number(link_or_number)
    if not number:
        st.caption(":material/warning: That is not a Companies House link or company number.")
        return
    codes = industry_codes(number)
    if isinstance(codes, str):
        st.caption(f":material/info: {codes}")
    elif not codes:
        st.caption(":material/info: Companies House lists no industry codes for this company.")
    else:
        st.markdown("**Industry (SIC codes on Companies House)**  \n" + "  \n".join(
            f":blue-badge[{code}] {meaning}" for code, meaning in codes))

st.set_page_config(page_title="Clario KYC workspace", page_icon=":material/fact_check:", layout="wide")
st.title("Clario KYC workspace")
st.caption(
    "Add everything you have for a company. Claude identifies each document, suggests the industry, and maps the evidence to "
    "every item of the matching KYC checklist; fixed rules and the live Companies House register check the legal-existence items. "
    "Every result says why, and where it came from."
)

# --- 1. Documents and links ---

with st.container(border=True):
    st.subheader(":material/upload_file: 1. Add the company's documents and links")
    source = st.segmented_control(
        "Documents", ["Sample pack", "Upload documents"], default="Sample pack", key="source"
    ) or "Sample pack"

    if source == "Sample pack":
        documents = [UploadedDocument(f.name, f.read_bytes()) for f in SAMPLE_FILES]
        saved_answers = SAMPLE_ANSWERS
        st.caption(
            f"{len(documents)} specimen documents for the fictitious EXAMPLE PAYMENTS LTD, with deliberate gaps. "
            "Saved answers are replayed, so the sample costs nothing to run."
        )
        st.pills("Files", [d.name for d in documents], disabled=True, label_visibility="collapsed")
    else:
        uploads = st.file_uploader("Company documents (PDFs or photos)", type=UPLOAD_TYPES, accept_multiple_files=True)
        documents = [UploadedDocument(u.name, u.getvalue(), u.type or "application/pdf") for u in uploads or []]
        saved_answers = {}
        st.caption(":material/lock: Only upload fictitious or approved documents: files are sent to Anthropic to be read.")

    company_link = st.text_input(
        "Companies House link or company number",
        value=SAMPLE_COMPANY_NUMBER if source == "Sample pack" else "",
        key=f"company_link_{source}",
        placeholder="e.g. 12345678 or https://find-and-update.company-information.service.gov.uk/company/12345678",
    )
    show_industry(company_link)
    website = st.text_input("Company website (optional)", key=f"website_{source}", placeholder="e.g. example.com")
    st.text_input("FCA register link", disabled=True, placeholder="Coming soon",
                  help="Needs a free FCA API key; the FCA checks (Section 2) show as missing until then.")

# Start again whenever the set of documents changes
pack_key = pack_fingerprint(documents) if documents else None
if st.session_state.get("pack_key") != pack_key:
    st.session_state.pack_key = pack_key
    st.session_state.pop("identification", None)
    st.session_state.pop("assessment", None)

if not documents:
    st.info("Add at least one document to continue.", icon=":material/info:")
    st.stop()

# --- 2. Identify documents ---

with st.container(border=True):
    st.subheader(":material/plagiarism: 2. Check what each document is")
    if "identification" not in st.session_state:
        st.caption(f"Claude reads the {len(documents)} files and labels each one (roughly 1p per document).")
        if not st.button("Identify documents", type="primary", icon=":material/search:"):
            st.stop()
        with st.spinner("Claude is reading the documents..."):
            try:
                st.session_state.identification = identify_documents(documents, saved_answer=saved_answers.get("labels"))
            except (ExtractionFailed, UnsupportedFile) as error:
                st.error(f"Could not identify the documents: {error}", icon=":material/error:")
                st.stop()

    identification = st.session_state.identification
    st.caption("Change a label if Claude got it wrong. The checks use these labels.")
    edited = st.data_editor(
        pd.DataFrame(
            [{"File": label.name, "Document type": label.type_label, "Why": label.reason}
             for label in identification.labels]
        ),
        column_config={
            "Document type": st.column_config.SelectboxColumn(options=list(DOCUMENT_TYPES.values()), required=True),
            "Why": st.column_config.TextColumn("Why Claude thinks so"),
        },
        disabled=["File", "Why"],
        hide_index=True,
        key=f"labels_{pack_key}",
    )
    confirmed = [
        DocumentLabel(row["File"], TYPE_KEY[row["Document type"]], row["Why"]) for _, row in edited.iterrows()
    ]
    st.caption(
        "Labels: replayed, $0.00" if identification.replayed
        else f"Labels: about ${identification.cost_usd:.3f}"
    )

# --- 3. Industry ---

links_key = (tuple(confirmed), company_link.strip(), website.strip())
if st.session_state.get("industry") and st.session_state.industry[0] != links_key:
    st.session_state.pop("industry")  # documents, labels or links changed

with st.container(border=True):
    st.subheader(":material/domain: 3. Confirm the industry and checklist")
    if "industry" not in st.session_state:
        st.caption(
            "Claude reads the questionnaire, the Companies House record (including its industry codes) and the website, "
            "and suggests which industry the company is in (roughly 1-2p)."
        )
        if not st.button("Suggest the industry", type="primary", icon=":material/search:"):
            st.stop()
        sources, link_warnings = fetch_links(company_link, website)
        for warning in link_warnings:
            st.warning(warning, icon=":material/warning:")
        with st.spinner("Claude is working out the industry..."):
            try:
                suggestion = suggest_industry(documents, confirmed, sources, saved_answer=saved_answers.get("industry"))
            except (ExtractionFailed, UnsupportedFile) as error:
                st.error(f"Could not suggest the industry: {error}", icon=":material/error:")
                st.stop()
        st.session_state.industry = (links_key, suggestion)

    suggestion = st.session_state.industry[1]
    st.markdown(f"**Claude suggests:** {suggestion.industry_label}  \n{suggestion.reason}")
    if suggestion.sources_agree == "no":
        st.warning(f"**The sources disagree.** {suggestion.disagreement}", icon=":material/warning:")
    else:
        st.caption(SOURCES_AGREE[suggestion.sources_agree])
    if suggestion.evidence:
        with st.expander("Evidence"):
            st.markdown("\n".join(f"- {quote}" for quote in suggestion.evidence))
    industry = INDUSTRY_KEY[st.selectbox(
        "Industry", list(INDUSTRIES.values()), index=list(INDUSTRIES).index(suggestion.industry),
        key=f"industry_{hash(links_key)}", help="Change this if Claude got it wrong.",
    )]
    suggested_checklist, written_for_industry = checklist_for(industry)
    checklist = CHECKLIST_KEY[st.selectbox(
        "Checklist", [name for name, _ in CHECKLISTS.values()], index=list(CHECKLISTS).index(suggested_checklist),
        key=f"checklist_{hash(links_key)}_{industry}",
        help="Suggested from the industry. Choose another if a different checklist fits the company better.",
    )]
    if not written_for_industry:
        st.caption(":material/info: There is no checklist written for this industry yet, so the fintech one is suggested.")
    if checklist != suggested_checklist:
        st.caption(":material/edit: You chose a different checklist from the one suggested for this industry.")
    st.caption(
        "Industry: replayed, $0.00" if suggestion.replayed
        else f"Industry: about ${suggestion.cost_usd:.3f}"
    )

# Results no longer match if the labels or the checklist changed
if st.session_state.get("assessment") and st.session_state.assessment[0] != (confirmed, checklist):
    st.session_state.pop("assessment")

# --- 4. Run the checks ---

with st.container(border=True):
    st.subheader(":material/fact_check: 4. Run the KYC checks")
    if "assessment" not in st.session_state:
        st.caption("Claude reads every document again against the checklist (roughly 2p per document).")
        replay_sample = source == "Sample pack" and checklist == SAMPLE_CHECKLIST
        if source == "Sample pack" and not replay_sample:
            st.caption(":material/payments: The sample's saved answer is for the fintech checklist; with this checklist "
                       "Claude is asked again (about 20p).")
        if not st.button("Run KYC checks", type="primary", icon=":material/play_arrow:"):
            st.stop()
        sources, _ = fetch_links(company_link, website)
        with st.spinner("Claude is mapping the evidence to the checklist..."):
            try:
                result = assess_pack(
                    documents, confirmed, sources, checklist=CHECKLISTS[checklist][1],
                    saved_answer=saved_answers.get("assessment") if replay_sample else None,
                )
            except ExtractionFailed as error:
                st.error(f"Could not run the checks: {error}", icon=":material/error:")
                st.stop()
        st.session_state.assessment = ((confirmed, checklist), result)
    result = st.session_state.assessment[1]
    total = identification.cost_usd + suggestion.cost_usd + result.cost_usd
    st.caption(
        "Checks: replayed, $0.00" if result.replayed
        else f"Checks: about ${result.cost_usd:.3f}. Total for this company: about ${total:.3f}"
    )

# --- Results ---

st.header("Results")
st.caption(
    f"Industry: {INDUSTRIES[industry]}. Checklist: {CHECKLISTS[checklist][0]} ({len(result.outcomes)} checks)"
    + (", chosen by you instead of the suggested one." if checklist != suggested_checklist else ".")
)
with st.container(horizontal=True):
    for status, help_text in [
        (Status.PRESENT, "The evidence is there and consistent"),
        (Status.MISSING, "Not provided"),
        (Status.UNCLEAR, "Incomplete, out of date or inconsistent"),
        (Status.NEEDS_HUMAN_REVIEW, "A judgement call for an analyst"),
        (Status.NOT_STARTED, "Screening and analyst decisions, done outside this tool"),
    ]:
        st.metric(STATUS_TEXT[status], result.count(status), help=help_text, border=True)

left, right = st.columns(2)
for column, title, icon, gaps, empty in [
    (left, "Request from client", ":material/mail:", result.request_from_client(), "Nothing to request."),
    (right, "Check on public registers", ":material/account_balance:", result.check_on_registers(), "Nothing to check."),
]:
    with column.container(border=True):
        st.subheader(f"{icon} {title}")
        if not gaps:
            st.success(empty, icon=":material/check_circle:")
        for outcome in gaps:
            st.markdown(f"**{outcome.check.id} · {outcome.check.evidence_source}**  \n{outcome.finding}")

st.subheader("Every check, by section")
for section, outcomes in groupby(result.outcomes, key=lambda o: o.check.section):
    outcomes = list(outcomes)
    present = sum(o.status is Status.PRESENT for o in outcomes)
    open_issues = sum(o.status in (Status.MISSING, Status.UNCLEAR, Status.NEEDS_HUMAN_REVIEW) for o in outcomes)
    label = f"{section} · {present} of {len(outcomes)} present" + (f" · {open_issues} to look at" if open_issues else "")
    with st.expander(label, expanded=open_issues > 0):
        st.dataframe(
            pd.DataFrame([
                {
                    "ID": o.check.id,
                    "Check": o.check.check,
                    "Status": STATUS_TEXT[o.status],
                    "Finding": o.finding,
                    "Evidence": o.evidence,
                    "Decided by": o.decided_by,
                    "Claude's view": o.claude_finding,
                }
                for o in outcomes
            ]),
            column_config={
                "Check": st.column_config.TextColumn(width="medium"),
                "Finding": st.column_config.TextColumn(width="large"),
                "Evidence": st.column_config.ListColumn(width="large"),
                "Claude's view": st.column_config.TextColumn(help="Shown when the fixed rules made the decision"),
            },
            hide_index=True,
        )

st.caption(
    "Items marked 🔎 must be reviewed by an analyst. Clario supports, and does not replace, a KYC review. "
    "Not legal advice."
)
