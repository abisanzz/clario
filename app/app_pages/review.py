"""Clario review page: add a company's details and documents, and see which checklist items are covered.

Opened from the menu in app/main.py. Run from the project folder:  .venv/bin/streamlit run app/main.py
"""

import re
import sys
from dataclasses import asdict, replace
from datetime import date
from itertools import groupby
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))  # so "services" can be imported when Streamlit runs this file

from services.companies_house import (  # noqa: E402
    CompanyNotFound,
    LookupFailed,
    get_company,
    get_officers,
    get_persons_with_significant_control,
    nature_of_business,
    parse_company_number,
)
from services.extractor import ExtractionFailed  # noqa: E402
from services.fca import FcaLookupFailed, FirmNotFound, get_firm, parse_frn  # noqa: E402
from app.session import discard_unsaved, open_assessment, unsaved_summary  # noqa: E402
from services.overview import summarise  # noqa: E402
from services.cycles import (  # noqa: E402
    approved_document,
    approved_snapshots,
    assessment_answer_path,
    attach_documents,
    cycle_review_id,
    cycle_started_on,
    copy_file,
    current_cycle,
    cycle_key,
    freeze,
    load_snapshot,
    load_submission,
    remove_snapshot,
    start_periodic_review,
    submit_for_approval,
    withdraw_submission,
)
from services.workflow import (  # noqa: E402
    REVIEW_YEARS,
    APPROVED,
    CANCELLED,
    DEFINITIONS,
    IN_PROGRESS,
    NOT_STARTED,
    ON_HOLD,
    PENDING_APPROVAL,
    REJECTED,
    UNDER_REVIEW,
    clear_status,
    load_status,
    next_review_date,
    set_status,
)
from services.audit import describe_line_change, events_csv, load_events, log_event  # noqa: E402
from services.cases import (  # noqa: E402
    DETAIL_FIELDS,
    add_documents,
    add_supporting_document,
    answer_paths,
    load_supporting,
    remove_supporting_document,
    find_case,
    list_cases,
    review_id,
    save_progress,
    save_review,
)
from services.checklist import CHECKLISTS, load_checks  # noqa: E402
from services.conversion import (  # noqa: E402
    CSV,
    UPLOAD_EXTENSIONS,
    XLSX,
    CannotRead,
    csv_rows,
    is_text_type,
    media_type_for,
    sheets,
    to_text,
)
from services.countries import COUNTRIES, UNITED_KINGDOM, is_uk  # noqa: E402
from services.demo import DEMO_NOTE, is_demo  # noqa: E402
from services.verification import check_facts, companies_house_record  # noqa: E402
from services.intelligence import key_facts, normalise, owners, people  # noqa: E402
from services.information import Row, from_documents_and_registers, provided_by_analyst, without_page  # noqa: E402
from services.industry import INDUSTRIES, SOURCES_AGREE, checklist_for, suggest_industry  # noqa: E402
from services.pack import (  # noqa: E402
    DOCUMENT_TYPES,
    DocumentLabel,
    LinkedSource,
    UnsupportedFile,
    UploadedDocument,
    apply_entity_name,
    assess_pack,
    companies_house_source,
    extract_details,
    fca_source,
    identify_documents,
    pack_fingerprint,
)
from services.reviews import (  # noqa: E402
    FinalApproval,
    save_override,
    approve_review,
    outstanding_lines,
    load_approval,
    withdraw_approval,
    apply_overrides,
    case_file,
    load_overrides,
    remove_override,
    save_line_reviews,
)
from services.risk import (  # noqa: E402
    evidence_path,
    NOT_ENOUGH,
    RATINGS,
    load_risk_decision,
    save_risk_decision,
    suggest_risk,
)
from services.supporting import read_supporting_document  # noqa: E402
from services.validator import Status, entity_name_matches  # noqa: E402
from services.website import WebsiteFetchFailed, website_text  # noqa: E402
from services.wording import product_voice  # noqa: E402

SAMPLES = PROJECT_ROOT / "sample_documents"
SAMPLE_FILES = [SAMPLES / "certificate_of_incorporation.pdf"] + sorted((SAMPLES / "pack").glob("*.pdf"))
SAMPLE_DOCUMENTS = [UploadedDocument(f.name, f.read_bytes()) for f in SAMPLE_FILES]
SAMPLE_ANSWERS = {
    "labels": SAMPLES / "pack_labels.answer.json",
    "industry": SAMPLES / "pack_industry.answer.json",
    "assessment": SAMPLES / "pack_assessment.answer.json",
    "risk": SAMPLES / "pack_risk.answer.json",
}
SAMPLE_ENTITY_NAME = "EXAMPLE PAYMENTS LTD"
SAMPLE_COMPANY_NUMBER = "99999901"
SAMPLE_FCA_FRN = "999999"  # the specimen FRN in the sample questionnaire; not on the FCA register
UPLOAD_TYPES = UPLOAD_EXTENSIONS  # PDFs, images, Word, Excel, CSV, text, emails and web pages

STATUS_TEXT = {  # plain words: the status drop-down can't show icons
    Status.PRESENT: "Present",
    Status.MISSING: "Missing",
    Status.UNCLEAR: "Unclear",
    Status.NEEDS_HUMAN_REVIEW: "Needs human review",
    Status.NOT_STARTED: "Not started",
}
STATUS_LOOK = {  # each status's colour and line icon, wherever Markdown is shown
    Status.PRESENT: ("green", ":material/check_circle:"),
    Status.MISSING: ("red", ":material/cancel:"),
    Status.UNCLEAR: ("orange", ":material/warning:"),
    Status.NEEDS_HUMAN_REVIEW: ("blue", ":material/person_search:"),
    Status.NOT_STARTED: ("gray", ":material/hourglass_empty:"),
}
STATUS_ICON = {status: f":{colour}[{icon}]" for status, (colour, icon) in STATUS_LOOK.items()}
STATUS_BADGE = {status: f":{colour}-badge[{icon} {STATUS_TEXT[status]}]"  # a coloured pill
                for status, (colour, icon) in STATUS_LOOK.items()}
TYPE_KEY = {label: key for key, label in DOCUMENT_TYPES.items()}
STATUS_FROM_TEXT = {text: status for status, text in STATUS_TEXT.items()}
INDUSTRY_KEY = {label: key for key, label in INDUSTRIES.items()}
SAMPLE_CHECKLIST = "fintech_high"  # the checklist the sample pack's saved answer was made with (rated High)


@st.cache_data(ttl=3600, max_entries=50, show_spinner="Checking Companies House, the FCA register and the website...")
def fetch_links(company_link: str, website: str, fca_frn: str = "") -> tuple[list[LinkedSource], list[str]]:
    """The Companies House record, FCA register entry and website text, plus a warning for each that could not be read."""
    sources, warnings = [], []
    if parse_company_number(company_link):
        try:
            sources.append(companies_house_source(company_link))
        except LookupFailed as error:
            warnings.append(f"Companies House could not be checked ({error}); continuing without it.")
    if parse_frn(fca_frn):
        try:
            sources.append(fca_source(fca_frn))
        except FcaLookupFailed as error:
            warnings.append(f"The FCA register could not be checked ({error}); continuing without it.")
    if website.strip():
        try:
            sources.append(LinkedSource("Company website", website_text(website)))
        except WebsiteFetchFailed as error:
            warnings.append(f"The website could not be read ({error}); continuing without it.")
    return sources, warnings


NOT_ON_REGISTER = "not on the register"


@st.cache_data(ttl=3600, max_entries=50, show_spinner="Looking up Companies House...")
def company_profile(company_number: str) -> dict | str:
    """The company's Companies House record, or NOT_ON_REGISTER, or a sentence saying why it could not be checked."""
    try:
        return get_company(company_number)
    except CompanyNotFound:
        return NOT_ON_REGISTER
    except LookupFailed as error:
        return str(error)


def cached_company(company_number: str) -> dict:
    """Companies House lookup for the rules, using the page's saved answer instead of asking again."""
    profile = company_profile(company_number)
    if profile == NOT_ON_REGISTER:
        raise CompanyNotFound(company_number)
    if isinstance(profile, str):
        raise LookupFailed(profile)
    return profile


def industry_codes(company_number: str) -> list[tuple[str, str]] | str:
    """The company's SIC codes with their meanings, or a sentence saying why there are none."""
    profile = company_profile(company_number)
    if profile == NOT_ON_REGISTER:
        return "This company is not on the Companies House register, so there are no industry codes."
    if isinstance(profile, str):
        return f"Companies House could not be checked ({profile})."
    return nature_of_business(profile)


def show_entity_name_check(entity_name: str, link_or_number: str) -> None:
    """Rule-based check: does the legal entity name entered match the name registered at Companies House?"""
    number = parse_company_number(link_or_number)
    if not entity_name.strip() or not number:
        return
    profile = company_profile(number)
    registered = profile.get("company_name", "") if isinstance(profile, dict) else ""
    if not registered:
        return  # not on the register, or not checked: the industry note above already says so
    if entity_name_matches(entity_name, registered):
        st.caption(f":material/check_circle: The legal entity name matches Companies House: {registered}")
    else:
        st.warning(f"The legal entity name entered does not match Companies House, which has **{registered}**. "
                   "Check the full registered legal name.", icon=":material/warning:")


@st.cache_data(ttl=3600, max_entries=50, show_spinner="Looking up the FCA register...")
@st.cache_data(ttl=3600, max_entries=50, show_spinner=False)
def register_record(company_number: str):
    """The live Companies House record used for external verification, or None if there isn't one."""
    return companies_house_record(company_number, get_company, get_officers, get_persons_with_significant_control)


def fca_status_of(frn: str) -> str:
    """The firm's status on the live FCA register, or "" if it wasn't checked or isn't there."""
    if not parse_frn(frn):
        return ""
    firm = fca_firm(frn)
    return firm.get("Status", "") if isinstance(firm, dict) else ""


def fact_checks(details: dict, link: str, frn: str) -> list:
    """The key facts with extraction, cross-document check and external verification kept apart."""
    number = parse_company_number(link) if link else None
    return check_facts(details, register_record(number) if number else None, fca_status_of(frn))


def fca_firm(frn: str) -> dict | str:
    """The firm's main FCA register entry, or a sentence saying why there is none."""
    try:
        return get_firm(frn)
    except FirmNotFound:
        return f"There is no firm with reference number {frn} on the FCA register."
    except FcaLookupFailed as error:
        return f"The FCA register could not be checked ({error})."


def show_fca_firm(text: str, company_link: str) -> None:
    """Show the firm's name and status under the FCA box, and flag a Companies House number that does not match."""
    if not text.strip():
        return
    frn = parse_frn(text)
    if not frn:
        st.caption(":material/warning: That is not an FCA firm reference number (6 or 7 digits).")
        return
    firm = fca_firm(frn)
    if isinstance(firm, str):
        st.caption(f":material/info: {firm}")
        return
    company_number = firm.get("Companies House Number") or ""
    st.markdown(
        f"**{firm.get('Organisation Name', 'Name not shown')}** :blue-badge[{firm.get('Status', 'status not shown')}]"
        + (f"  \nCompanies House number on the FCA register: {company_number}" if company_number else ""))
    entered = parse_company_number(company_link)
    if entered and company_number and company_number.upper() != entered:
        st.warning(f"The FCA register links this firm to company {company_number}, not {entered}. "
                   "Check you have the right firm.", icon=":material/warning:")


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

# Show each field's help "?" just after its label, with a small space, instead of at the far right of the row
st.html("""<style>
[data-testid="stWidgetLabel"] > div { flex: 0 0 auto; justify-content: flex-start; margin-left: 0.4rem; }
</style>""")

# --- Screen 1: Legal Entity Information ---
# Streamlit forgets the contents of fields that are not on screen, so "Next" saves them for the session

saved = st.session_state.get("entity", {})


def remembered(field: str, sample_value: str, source: str) -> str:
    """What to show in a field: what was entered before for this choice of documents, else the sample's value."""
    if saved.get("source") == source:
        return saved.get(field, "")
    return sample_value if source == "Sample pack" else ""


def save_draft(details: dict, documents: list[UploadedDocument]) -> None:
    """Save the review on this computer. One review per legal entity: this replaces any other saved review of it."""
    stored = documents if details["source"] == "Upload documents" else []  # the sample's files stay where they are
    is_new = not st.session_state.get("case_id")
    if is_new and details.get("owner"):
        st.session_state.last_reviewer = details["owner"]
    before = {d.fingerprint: d.name for d in saved.get("documents", [])} if not is_new else {}
    case_id = save_review(st.session_state.get("case_id"), details, stored)
    st.session_state.case_id = case_id
    log_path, who = case_file(case_id, "audit").with_suffix(".jsonl"), st.session_state.get("last_reviewer", "")
    if is_new:
        log_event(log_path, who, f"Created the assessment for {details['entity_name'] or 'an unnamed entity'}"
                  + (" (sample pack)" if details["source"] == "Sample pack" else ""))
    after = {d.fingerprint: d.name for d in stored}
    if not is_new and saved.get("owner") and details.get("owner") and details["owner"] != saved["owner"]:
        log_event(log_path, who, f"Changed the owner from {saved['owner']} to {details['owner']}")
    for fingerprint, name in after.items():
        if fingerprint not in before:
            log_event(log_path, who, f"Uploaded document {name}")
    for fingerprint, name in before.items():
        if fingerprint not in after:
            log_event(log_path, who, f"Removed document {name}")
    st.session_state.entity = {**details, "documents": stored, "supporting": saved.get("supporting", [])}


def draft_label(draft: dict) -> str:
    saved_at = draft["saved_at"].replace("T", " ")[:16]
    return (f"{draft['review_id']} · {draft['entity_name'] or 'Unnamed entity'} · {draft['documents']} documents · "
            f"saved {saved_at}")


def details_tab() -> None:
    """The legal entity's details and documents; Save and continue saves them as the review."""
    st.markdown(
        "Provide the details of the legal entity you are reviewing and upload the documents you hold for it. Clario "
        "uses them to establish the entity's identity, check it against Companies House and the FCA register, "
        "understand its ownership and structure, and map the evidence to the KYC checklist for its industry."
    )
    st.caption(
        "Make sure the details match the entity's official records. Where information is missing or inconsistent, "
        "Clario lists what to request from the client and what to check on public registers. Every finding shows "
        "where it came from, for you to validate."
    )
    owner = st.text_input(
        "Assessment owner", value=saved.get("owner") or st.session_state.get("last_reviewer", ""), key="owner",
        width=300,
        help="Whoever creates the assessment owns it. An analyst can reassign it to someone else; the change is "
             "recorded in the audit history when you save.",
    )
    with st.container(border=True):
        st.subheader(":material/upload_file: Legal Entity Information")
        # The documents choice sits below the fields but decides what they are filled with, so read its last setting
        source = st.session_state.get("source") or saved.get("source") or "Upload documents"
        if is_demo() and not st.session_state.get("case_id"):
            source = "Sample pack"  # the public demo uses the example case only

        entity_name = st.text_input(
            "Legal Entity Full Name",
            value=remembered("entity_name", SAMPLE_ENTITY_NAME, source),
            key=f"entity_name_{source}",
            help="Enter the full registered legal name of the entity you are conducting business with.",
        )
        known_country = remembered("country", UNITED_KINGDOM, source) or UNITED_KINGDOM
        country = st.selectbox(
            "Country of incorporation", COUNTRIES if known_country in COUNTRIES else [known_country] + COUNTRIES,
            index=(COUNTRIES.index(known_country) if known_country in COUNTRIES else 0), key=f"country_{source}",
            accept_new_options=True,
            help="Where the entity is registered. Choose from the list or type another country. Companies House and "
                 "FCA register checks apply to UK companies only.",
        ) or UNITED_KINGDOM
        registration_number = ""
        if is_uk(country):
            company_link = st.text_input(
                "Companies House Link or Company Number",
                value=remembered("company_link", SAMPLE_COMPANY_NUMBER, source),
                key=f"company_link_{source}",
                placeholder="e.g. 12345678 or https://find-and-update.company-information.service.gov.uk/company/12345678",
                help="Enter a link to the company’s Companies House record or its company registration number. "
                     "We’ll use this to find the company’s details on Companies House.",
            )
            show_industry(company_link)
            show_entity_name_check(entity_name, company_link)
        else:
            company_link = ""
            registration_number = st.text_input(
                "Company registration number", value=remembered("registration_number", "", source),
                key=f"registration_{source}", placeholder="e.g. 654321",
                help=f"The entity's number on the company register in {country}.",
            )
            st.caption(f":material/info: Incorporated in {country}: Companies House and the FCA register are not "
                       "checked. Check the entity on its home country's register.")
        website = st.text_input("Company website", value=remembered("website", "", source), key=f"website_{source}",
                                placeholder="e.g. example.com")
        if is_uk(country):
            fca_frn = st.text_input(
                "FCA firm reference number", key=f"fca_{source}", placeholder="e.g. 730427",
                value=remembered("fca_frn", SAMPLE_FCA_FRN, source),
                help="The 6 or 7 digit FRN on the firm's FCA register page. Leave empty if the firm is not FCA "
                     "regulated.",
            )
            show_fca_firm(fca_frn, company_link)
        else:
            fca_frn = ""
        known_industry = remembered("stated_industry", "", source)
        stated_industry = st.selectbox(
            "Industry", list(INDUSTRIES), format_func=INDUSTRIES.get,
            index=list(INDUSTRIES).index(known_industry) if known_industry in INDUSTRIES else None,
            key=f"stated_industry_{source}", placeholder="Not sure: Clario will suggest one",
            help="If you know it. Clario still suggests an industry from the documents, and you confirm it at Risk "
                 "assessment.",
        ) or ""
        existing = find_case({"entity_name": entity_name, "company_link": company_link})
        if existing and existing["id"] != st.session_state.get("case_id"):
            with st.container(border=True):
                st.warning(
                    f"A saved review already exists for {existing['entity_name'] or 'this entity'} "
                    f"({draft_label(existing)}). Each legal entity has one review, so saving this one will replace "
                    "it. To add to the saved review instead, open it.", icon=":material/warning:")
                if st.button("Open the saved review", icon=":material/folder_open:"):
                    open_assessment(existing["id"])
                    st.rerun()

        if st.session_state.get("case_id"):  # a saved review keeps its own documents: no switching to the example
            source = saved.get("source") or "Upload documents"
            st.markdown("**Documents**")
        elif is_demo():  # the public demo: the example case only, so no client documents are uploaded
            source = "Sample pack"
            st.markdown("**Documents**")
            st.caption(":material/info: The public demo uses the example case. Run Clario on your own computer to "
                       "review a client's documents.")
        else:  # a new assessment: the client's documents, or the example case for training and walkthroughs
            source = st.segmented_control(
                "Documents", ["Upload documents", "Sample pack"], default=saved.get("source", "Upload documents"),
                key="source",
                format_func=lambda choice: {"Sample pack": "Example case", "Upload documents": "Client documents"}[choice],
            ) or "Upload documents"
        if source == "Sample pack":
            documents = SAMPLE_DOCUMENTS
            st.caption(
                f"The {len(documents)}-document example case for EXAMPLE PAYMENTS LTD, used for training and "
                "walkthroughs. It includes typical gaps an analyst would raise with the client."
            )
            st.pills("Files", [d.name for d in documents], disabled=True, label_visibility="collapsed")
        else:
            earlier = saved.get("documents", []) if saved.get("source") == "Upload documents" else []
            kept = []
            if earlier:
                names = st.multiselect("Documents in this review", [d.name for d in earlier],
                                       default=[d.name for d in earlier], key="kept_documents",
                                       help="Remove a document by clicking its ×. Add more below.")
                kept = [d for d in earlier if d.name in names]
            uploads = None if is_demo() else st.file_uploader(
                "Add documents" if earlier else "Company documents",
                help="PDFs, Word (.docx), Excel (.xlsx), CSV, text, emails (.eml), web pages (.html) or photos (PNG, "
                     "JPEG, WebP, GIF).",
                type=UPLOAD_TYPES, accept_multiple_files=True)
            added = [UploadedDocument(u.name, u.getvalue(), media_type_for(u.name, u.type)) for u in uploads or []]
            added_names = {d.name for d in added}
            documents = [d for d in kept if d.name not in added_names] + added  # a new file replaces one with its name
            if documents:  # what each document shows, in the analyst's words (optional)
                st.markdown("**What does each document show?** (optional)")
                described = []
                for document in documents:
                    name_side, description_side = st.columns([2, 3], vertical_alignment="center")
                    name_side.caption(f":material/description: {document.name}")
                    text = description_side.text_input(
                        f"What does {document.name} show? (optional)", value=document.description,
                        key=f"doc_description_{document.fingerprint}", label_visibility="collapsed",
                        placeholder="What does this document show? e.g. Register of members, dated 20 Oct 2026",
                        help="Clario AI reads this as a hint when identifying the document and running the checks.")
                    described.append(replace(document, description=text.strip()))
                documents = described
            st.caption(
                ":material/lock: Documents are processed by Clario's AI service. Upload only documents your "
                "data-handling policy permits.")

    details = {"source": source, "entity_name": entity_name, "company_link": company_link, "website": website,
               "fca_frn": fca_frn, "country": country, "registration_number": registration_number,
               "stated_industry": stated_industry, "owner": owner.strip()}
    with st.container(horizontal=True):
        if st.button("Save as draft", icon=":material/save:", disabled=not owner.strip()):
            save_draft(details, documents)
            st.toast(f"Draft saved: {review_id(st.session_state.case_id)}. Find it any time in Assessments.",
                     icon=":material/check_circle:")
        if st.button("Save and continue", type="primary", icon=":material/arrow_forward:",
                     disabled=not documents or not owner.strip()):
            save_draft(details, documents)  # every review is saved, so it can be reopened and amended later
            go("documents")
    if not owner.strip():
        st.caption("Enter the assessment owner to save.")
    elif not documents:
        st.caption("Add at least one document to continue.")
    else:
        st.caption("Save and continue: Clario identifies each document and extracts its key details.")
    st.stop()

# --- The assessment's tabs ---

TAB_NAMES = ["Details & documents", "Document intelligence", "Risk assessment", "Evidence review",
             "Ongoing monitoring", "Audit history"]
SCREENS = ["details", "documents", "assess", "results", "monitoring", "audit"]


def leaving_with_unsaved(target: str) -> bool:
    """Is the user leaving a tab that has checklist changes they have not saved?"""
    here = st.session_state.get("current_tab")
    return target != here and here in {c["tab"] for c in st.session_state.get("unsaved_lines", {}).values()}


def go(to: str) -> None:
    """Switch to another tab (applied before the tabs are drawn on the next run). With unsaved checklist changes,
    the user is asked first."""
    target = TAB_NAMES[SCREENS.index(to)]
    if leaving_with_unsaved(target):
        st.session_state.leave_to = target
    else:
        st.session_state.switch_tab = target
    st.rerun()


def tab_key() -> str:
    """The tab bar's key. It changes when Clario puts the user back on a tab, so the browser redraws the tab bar:
    a tab set straight back to the one it was on is otherwise not passed to the browser."""
    return f"assessment_tab_{st.session_state.get('tab_version', 0)}"


def remember_tab() -> None:
    chosen = st.session_state[tab_key()]
    if leaving_with_unsaved(chosen):  # stay on this tab until the user decides about the unsaved changes
        st.session_state.leave_to = chosen
        st.session_state.switch_tab = st.session_state.current_tab
        st.session_state.tab_version = st.session_state.get("tab_version", 0) + 1
    else:
        st.session_state.current_tab = chosen


@st.dialog("Document", icon=":material/description:", width="large")
def view_document(name: str, data: bytes, media_type: str) -> None:
    """Show a document's content: a PDF's pages, or the image itself."""
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown(f"**{name}**", width="stretch")
        st.download_button("Download", data, file_name=name, mime=media_type, icon=":material/download:")
    try:
        if media_type == "application/pdf":
            st.pdf(data, height=720)
        elif media_type.startswith("image/"):
            st.image(data)
        elif media_type == XLSX:
            for sheet, rows in sheets(data):
                st.markdown(f"**Sheet: {sheet}**")
                st.dataframe(pd.DataFrame(rows), hide_index=True)
        elif media_type == CSV:
            st.dataframe(pd.DataFrame(csv_rows(data)), hide_index=True)
        elif is_text_type(media_type):
            with st.container(border=True, height=620):
                st.text(to_text(name, data, media_type))
        else:
            st.info("This type of file can't be shown here. Download it to open it.", icon=":material/info:")
    except CannotRead as error:
        st.warning(f"{error}. Download it to open it.", icon=":material/warning:")


@st.dialog("Unsaved changes", icon=":material/warning:", dismissible=False, width="medium")
def unsaved_dialog(target: str) -> None:
    st.warning("Some checklist changes have not been saved. Continuing without saving will lose them.",
               icon=":material/warning:")
    unsaved_summary()
    stay, leave = st.columns(2)
    if stay.button("Stay and save", type="primary", icon=":material/edit_note:", width="stretch"):
        st.session_state.pop("leave_to", None)
        st.rerun()
    if leave.button("Leave without saving", icon=":material/logout:", width="stretch"):
        discard_unsaved()
        st.session_state.switch_tab = target
        st.rerun()


def make_tabs():
    """The tabs; only the open tab's content runs, so paid steps start only when their tab is opened. The open tab
    is remembered, so it stays open after saving or any other change."""
    if "switch_tab" in st.session_state:
        st.session_state.current_tab = st.session_state.pop("switch_tab")
    if st.session_state.get("current_tab") in TAB_NAMES:
        st.session_state[tab_key()] = st.session_state.current_tab
    return st.tabs(TAB_NAMES, key=tab_key(), on_change=remember_tab)


if not saved:  # a new assessment: only the details tab can be used until it is saved
    st.title("New KYC assessment")
    new_tabs = make_tabs()
    with new_tabs[0]:
        if new_tabs[0].open:
            details_tab()
    for tab in new_tabs[1:]:
        with tab:
            if tab.open:
                st.info("Fill in **Details & documents** and click **Save and continue** first.",
                        icon=":material/info:")
    st.stop()

source = saved["source"]
entity_name, company_link, website, fca_frn = (saved[k] for k in ("entity_name", "company_link", "website", "fca_frn"))
documents = (SAMPLE_DOCUMENTS if source == "Sample pack" else saved["documents"]) + saved.get("supporting", [])
# The example case replays the answers that ship with it; once documents are added to it, its answers are saved in
# the review's own folder instead, so the shipped ones are never overwritten
saved_answers = (SAMPLE_ANSWERS if source == "Sample pack" and not saved.get("supporting")
                 else answer_paths(st.session_state.case_id))


def navigation(next_label: str | None = None, next_ready: bool = True, save=None) -> None:
    """Back and Next buttons. save runs first on either, so this screen's choices are kept whichever way you go.
    If save returns False (something is missing), Next stays on this screen and Back goes back without saving."""
    position = SCREENS.index(screen)
    with st.container(horizontal=True):
        if st.button("Back", icon=":material/arrow_back:", key=f"back_{screen}"):
            if save and next_ready:
                save(quiet=True)
            go(SCREENS[position - 1])
        if next_label and st.button(next_label, type="primary", icon=":material/arrow_forward:",
                                    disabled=not next_ready, key=f"next_{screen}"):
            if save and save() is False:
                return
            go(SCREENS[position + 1])


st.title(entity_name or "Legal entity")
country = saved.get("country") or UNITED_KINGDOM
summary = [("Incorporated in", country), ("Company", company_link),
           ("Registration number", saved.get("registration_number", "")), ("FCA FRN", fca_frn), ("Website", website),
           ("Documents", f"{len(documents)} files")]
st.caption(" · ".join(f"{label}: {value}" for label, value in summary if value))
# Start again whenever the set of documents changes
pack_key = pack_fingerprint(documents)
# Line reviews, the risk decision and the final approval belong to the review, so adding documents keeps them
review_key = st.session_state.get("case_id") or pack_key
audit_path = case_file(review_key, "audit").with_suffix(".jsonl")  # who changed what, and when
# Each review cycle (onboarding, then each periodic review) has its own line reviews, risk decision and approval
cycle = current_cycle(review_key)
cycle_review_key = cycle_key(review_key, cycle)


def cycle_name(number: int) -> str:
    return "Onboarding review" if number == 1 else f"Periodic review {number - 1}"


if st.session_state.get("case_id"):
    # Each review has its own ID; a periodic review's ID links it to the original, e.g. CLR-9580685D-PR1
    linked = ""
    if cycle > 1:
        previous = load_snapshot(review_key, cycle - 1)
        linked = (f" · {cycle_name(cycle)} of **{cycle_review_id(review_key, cycle - 1)}**"
                  + (f", approved on {previous.approved_on}" if previous else ""))
    st.caption(f":material/badge: Review ID **{cycle_review_id(review_key, cycle)}**{linked} · "
               ":material/cloud_done: All changes saved")

# --- The assessment's status, and putting it on hold, cancelling, resuming or reopening it ---
STATUS_COLOURS = {NOT_STARTED: "gray", IN_PROGRESS: "blue", UNDER_REVIEW: "violet", PENDING_APPROVAL: "orange",
                  APPROVED: "green", REJECTED: "red", ON_HOLD: "orange", CANCELLED: "gray"}
status_path = case_file(review_key, "status")
this_case = next((d for d in list_cases() if d["id"] == st.session_state.get("case_id")), None)
current = summarise(this_case) if this_case else None
if current:
    manual = load_status(status_path)
    with st.container(horizontal=True, vertical_alignment="center"):
        st.badge(current.status, color=STATUS_COLOURS[current.status], help=DEFINITIONS[current.status])
        if manual:
            st.caption(f"{manual.status} by {manual.by} on {manual.on}: {manual.reason}")
        elif current.next_review:
            st.caption(f"Next review due {current.next_review}")
        with st.popover("Status", icon=":material/tune:"):
            if manual:
                undo = "Resume" if manual.status == ON_HOLD else "Reopen"
                st.caption(f"This assessment is {manual.status.lower()}. {undo} it to carry on; its status will "
                           "follow the work again.")
                who = st.text_input("Your name", value=st.session_state.get("last_reviewer", ""), key="status_who")
                if st.button(undo, type="primary", icon=":material/play_arrow:", disabled=not who.strip()):
                    clear_status(status_path)
                    log_event(audit_path, who, f"{'Resumed' if undo == 'Resume' else 'Reopened'} the assessment "
                              f"(was {manual.status})")
                    st.rerun()
            else:
                action = st.segmented_control("Change the status", [ON_HOLD, CANCELLED], key="status_action",
                                              format_func=lambda a: "Put on hold" if a == ON_HOLD
                                              else "Cancel assessment")
                if action:
                    st.caption(DEFINITIONS[action])
                    reason = st.text_area("Reason", key="status_reason", height=80)
                    who = st.text_input("Your name", value=st.session_state.get("last_reviewer", ""),
                                        key="status_who")
                    sure = action != CANCELLED or st.checkbox("Yes, cancel this assessment", key="status_sure")
                    if st.button("Confirm", type="primary", icon=":material/check:", disabled=not sure):
                        try:
                            set_status(status_path, action, reason, who)
                        except ValueError as error:
                            st.error(str(error), icon=":material/error:")
                        else:
                            log_event(audit_path, who, f"Marked the assessment {action}: {reason.strip()}")
                            st.rerun()

stored_supporting = load_supporting(st.session_state.case_id) if st.session_state.get("case_id") else []
original_documents = SAMPLE_DOCUMENTS if source == "Sample pack" else saved["documents"]


def quotes_from(name: str, evidence: list[str]) -> bool:
    """Does any quoted evidence come from this document? Quotes start with the document's name."""
    return any(quote.startswith((f"{name}:", f"{name} p.")) for quote in evidence)


def lines_review_path() -> Path | None:
    chosen_checklist = st.session_state.get("choice", (None, None))[1]
    return case_file(cycle_review_key, chosen_checklist) if chosen_checklist else None


def dependants(document: UploadedDocument) -> list[str]:
    """What this document was used for: the industry, the risk rating, checklist lines, or lines it set to Present."""
    name, found = document.name, []
    if st.session_state.get("industry") and quotes_from(name, st.session_state.industry[1].evidence):
        found.append("**the industry suggestion**")
    if st.session_state.get("risk"):
        rated = st.session_state.risk[1]
        factors = [f.factor.name for f in rated.factors if quotes_from(name, f.evidence)]
        triggers = [f"EDD trigger {t.trigger.id}" for t in rated.triggers if quotes_from(name, t.evidence)]
        if factors or triggers:
            found.append("**the risk rating**: " + "; ".join(filter(None, [", ".join(factors), ", ".join(triggers)])))
    if st.session_state.get("assessment"):
        lines_used = [o.check.id for o in st.session_state.assessment[1].outcomes if quotes_from(name, o.evidence)]
        if lines_used:
            found.append("**checklist lines** " + ", ".join(lines_used))
    path = lines_review_path()
    if path:
        for override in load_overrides(path).values():
            if override.via == name:
                found.append(f"**line {override.check_id}**, which was set to Present from this document; it will go "
                             f"back to {override.original_status.value}")
    return found


def delete_documents(chosen: list[tuple[UploadedDocument, dict | None]]) -> None:
    """Delete documents from the review. Deleting an original document means the rest are identified and checked
    again; a line that a supporting document set to Present goes back to its previous status."""
    who = st.session_state.get("last_reviewer", "")
    supporting_gone = {d.fingerprint for d, record in chosen if record}
    originals_gone = {d.fingerprint for d, record in chosen if not record}
    path = lines_review_path()
    for document, record in chosen:
        if record:
            remove_supporting_document(st.session_state.case_id, document.fingerprint)
            for override in list(load_overrides(path).values()) if path else []:
                if override.via == document.name:
                    remove_override(path, override.check_id)
                    log_event(audit_path, who, f"Line went back to {override.original_status.value} because "
                              f"{document.name} was deleted", override.check_id)
        log_event(audit_path, who, f"Deleted document {document.name}",
                  f"check {record['check_id']}" if record else "")
    entity = {**saved, "supporting": [d for d in saved.get("supporting", []) if d.fingerprint not in supporting_gone]}
    if originals_gone:
        entity["documents"] = [d for d in saved["documents"] if d.fingerprint not in originals_gone]
        save_review(st.session_state.case_id, {k: saved[k] for k in DETAIL_FIELDS}, entity["documents"])
        if not entity["documents"]:
            st.session_state.switch_tab = "Details & documents"
    st.session_state.entity = entity
    st.session_state.pop("delete_pending", None)


class NotSavedYet(Exception):
    """A step that has no saved answer to replay."""


class ReplayOnly:
    """Stands in for the AI service when reopening a saved assessment: saved answers replay for free, and a step
    with no saved answer stops here instead of calling the paid service."""

    class _Messages:
        def create(self, **_):
            raise NotSavedYet

    beta = type("Beta", (), {"messages": _Messages()})()


def replay_only(step):
    try:
        return step()
    except NotSavedYet:
        return None


with st.expander(f"Documents ({len(original_documents) + len(stored_supporting)})", icon=":material/folder_open:"):
    rows = [(d, None) for d in original_documents] + list(stored_supporting)
    st.caption("Select a document to view it, or select documents to delete.")
    picked_documents = st.dataframe(pd.DataFrame([{
        "File": document.name,
        "Your description": (record.get("description", "") if record else document.description) or "",
        "Supports": ((f"Check {record['check_id']}" if record["check_id"] else "Added to the review")
                     if record else "Original document"),
    } for document, record in rows]), hide_index=True, height="content", on_select="rerun",
        selection_mode="multi-row", key=f"documents_{pack_key}_{len(rows)}")
    ticked = [rows[i] for i in picked_documents.selection.rows]
    with st.container(horizontal=True):
        if st.button("View", icon=":material/visibility:", type="primary", disabled=len(ticked) != 1,
                     help="Select one document to view its content."):
            view_document(ticked[0][0].name, ticked[0][0].data, ticked[0][0].media_type)
        if st.button("Delete selected", icon=":material/delete:", disabled=not ticked):
            st.session_state.delete_pending = [document.fingerprint for document, _ in ticked]
    pending = [(d, r) for d, r in rows if d.fingerprint in st.session_state.get("delete_pending", [])]
    if pending:
        deletable = [(d, r) for d, r in pending if r or source != "Sample pack"]
        skipped = [d.name for d, r in pending if not (r or source != "Sample pack")]
        with st.container(border=True):
            message = []
            for document, record in deletable:
                used_for = dependants(document)
                message.append(f"**{document.name}**" + (
                    " was used for:" + "".join(f"\n  - {item}" for item in used_for) if used_for else
                    ": not used for any result"))
            st.warning(
                ("Delete these documents?\n\n" + "\n".join(f"- {m}" for m in message)
                 + "\n\nDeleting them will change anything listed: it will be worked out again without them."
                 + ("  \nThe remaining documents will be identified and checked again. Your line reviews, risk "
                    "rating and approval are kept."
                    if any(not r for _, r in deletable) else "") if deletable else "Nothing can be deleted.")
                + (f"  \nThe example case's documents cannot be deleted, so these will be skipped: "
                   f"{', '.join(skipped)}."
                   if skipped else ""),
                icon=":material/delete:")
            with st.container(horizontal=True):
                if deletable and st.button("Yes, delete", type="primary", key="confirm_delete"):
                    delete_documents(deletable)
                    st.rerun()
                if st.button("Cancel", key="cancel_delete"):
                    st.session_state.pop("delete_pending", None)
                    st.rerun()

    # Add documents, from any tab: saved to the review's document store, then every document is read again on
    # Document intelligence. "\$" keeps the dollar signs from being read as a formula.
    if is_demo():
        st.caption(f":material/note_add: Adding documents: {DEMO_NOTE}")
    elif st.session_state.get("case_id"):
        st.markdown("**:material/note_add: Add documents**")
        st.caption("Added to the review's document store, then Clario AI reads all the documents again on Document "
                   "intelligence, so the document types and key facts update (about \\$0.10 to \\$0.15). The "
                   "document types you corrected and your comments are kept.")
        new_files = st.file_uploader("Documents to add", type=UPLOAD_TYPES, accept_multiple_files=True,
                                     key=f"add_to_pack_{pack_key}")
        new_description = st.text_input("What do they show? (optional)", key=f"add_to_pack_note_{pack_key}",
                                        placeholder="e.g. Updated register of members, dated 20 Oct 2026",
                                        help="Saved with the documents and shown in the list above.")
        if st.button("Add and re-read the documents", icon=":material/note_add:", disabled=not new_files):
            who = st.session_state.get("last_reviewer", "")
            taken = add_documents(st.session_state.case_id,
                                  [UploadedDocument(f.name, f.getvalue(), media_type_for(f.name, f.type))
                                   for f in new_files],
                                  {document.name for document, _ in rows}, who, new_description)
            if taken:
                st.error("Already in this review: " + ", ".join(taken) + ". Rename the file to add it as another "
                         "document.", icon=":material/error:")
            else:
                log_event(audit_path, who, f"Added {len(new_files)} document(s) to the review: "
                          + ", ".join(f.name for f in new_files) + "; all documents to be read again")
                # Keep the document types already corrected, then read every document again on Document intelligence
                st.session_state.label_corrections = {**st.session_state.get("label_corrections", {}),
                                                      **{label.name: label for label in
                                                         st.session_state.get("labels") or []}}
                st.session_state.entity = {**saved, "supporting": [document for document, _ in
                                                                   load_supporting(st.session_state.case_id)]}
                go("documents")
if st.session_state.get("pack_key") != pack_key:
    st.session_state.pack_key = pack_key
    for key in ("identification", "labels", "industry", "choice", "assessment"):
        st.session_state.pop(key, None)

def remember(**choices) -> None:
    """Keep the reviewer's label corrections or industry choice for this session, and in the draft if there is one."""
    st.session_state.update(choices)
    if st.session_state.get("case_id"):
        save_progress(st.session_state.case_id, pack_key, st.session_state.get("labels"),
                      st.session_state.get("choice"), comments=st.session_state.get("label_comments"))


tabs = make_tabs()
if st.session_state.get("leave_to"):
    unsaved_dialog(st.session_state.leave_to)
open_index = next((i for i, tab in enumerate(tabs) if tab.open), 0)
screen, open_tab = SCREENS[open_index], tabs[open_index]

with tabs[0]:
    if tabs[0].open:
        details_tab()

with tabs[5]:
    if tabs[5].open:
        events = load_events(audit_path)
        st.subheader(":material/history: Audit history")
        st.caption("Every change to this assessment, with who made it and when. Entries are only ever added.")
        if events:
            st.dataframe(pd.DataFrame([{"Time": e.at, "Who": product_voice(e.who), "Line": e.line,
                                       "What": product_voice(e.what)} for e in events]),
                         hide_index=True, column_config={"What": st.column_config.TextColumn(width="large")})
            st.download_button("Download the audit log (CSV)", events_csv(events), file_name="clario-audit-log.csv",
                               mime="text/csv", icon=":material/download:")
        else:
            st.caption("Nothing recorded yet.")
        st.stop()


def needs_first(tab: str, step: str) -> None:
    """Shown in the open tab when it needs an earlier tab completed first."""
    with open_tab:
        st.info(f"Complete the **{TAB_NAMES[SCREENS.index(step)]}** tab first.", icon=":material/info:")
        if st.button(f"Go to {TAB_NAMES[SCREENS.index(step)]}", key=f"needs_{tab}_{step}"):
            go(step)
    st.stop()


# --- Screen 2: what each document is, and the key details each one shows ---


def detail_lines(found) -> list[str]:
    lines = [f"**{title}:** {value}" for title, value in [
        ("Company name", found.company_name), ("Registration number", found.registration_number),
        ("Registered address", found.registered_address), ("Document date", found.document_date)] if value]
    if found.people:
        lines.append("**People:** " + "; ".join(f"{name} ({role})" if role else name for name, role in found.people))
    if found.owners:
        lines.append("**Owners:** " + "; ".join(f"{name}: {share}" if share else name for name, share in found.owners))
    return lines


def as_written(text: str) -> str:
    """Text from a document, shown exactly as printed: a table reads Markdown, so its symbols are escaped."""
    return re.sub(r"([\\`*_{}\[\]<>()#+\-.!|~$:])", r"\\\1", text)


class Shown(str):
    """A table cell Clario wrote itself, with an icon: its Markdown is shown as it is, not escaped."""


def with_icon(icon: str, text: str) -> Shown:
    return Shown(f"{icon} {as_written(text)}")


def fit_table(rows: list[dict]) -> None:
    """A small read-only table that wraps long text to fit the page, each cell shown as written."""
    st.table(pd.DataFrame([{column: value if isinstance(value, Shown) else as_written(str(value))
                            for column, value in row.items()} for row in rows]),
             hide_index=True, border="horizontal")


def show_key_facts(identification) -> None:
    """The details from every document side by side, with what they disagree on flagged. A fold-out, minimised to
    start with; its title says when the documents disagree or the details have not been extracted yet."""
    title = "**Key facts across the documents**"
    if not identification.extracted:
        title += " · not extracted yet"
    else:
        disagree = [fact.fact for fact in key_facts(identification.details) if fact.disagree]
        if any(len(shares) > 1 for _, shares in owners(identification.details)):
            disagree.append("Ownership")
        if disagree:
            title += f" · :orange[documents disagree on {', '.join(disagree)}]"
    with st.expander(title, icon=":material/manage_search:", expanded=False):
        if not identification.extracted:
            st.caption("Key details (company name, registration number, address, dates, people and owners) have not "
                       "been extracted for these documents yet. Extract them to compare the documents; the document "
                       "types stay as they are.")
            if is_demo():
                st.caption(DEMO_NOTE)
            elif st.button("Extract the details", icon=":material/manage_search:"):
                with st.spinner(f"Clario is extracting the details from {len(documents)} documents..."):
                    try:
                        st.session_state.identification = extract_details(
                            documents, identification, saved_answer=saved_answers.get("labels"))
                    except (ExtractionFailed, UnsupportedFile) as error:
                        st.error(f"Could not extract the details: {error}", icon=":material/error:")
                    else:
                        log_event(audit_path, "Clario", f"Extracted the details of {len(documents)} documents "
                                  f"(AI usage ${st.session_state.identification.cost_usd:.3f})")
                        st.rerun()
            return
        details = identification.details
        facts = key_facts(details)
        if not facts and not people(details) and not owners(details):
            st.caption("No company details were found in these documents.")
            return
        st.caption("**Extracted:** what the documents say, as printed. **Across documents:** whether they agree "
                   "(capitals, punctuation and Limited/Ltd are ignored). **External verification:** only a live "
                   "Companies House or FCA register check counts; documents the customer supplied never do.")
        names = {normalise(value) for fact in facts if fact.fact == "Company name" for value in fact.values}
        if entity_name.strip() and names and normalise(entity_name) not in names:
            st.warning(f"**The Legal Entity name you entered ({entity_name}) is not the name on the documents.**",
                       icon=":material/warning:")
        for fact in facts:
            if fact.disagree:
                st.warning(f"**{fact.fact}: the documents disagree.**\n" + "\n".join(
                    f"- {value}: {', '.join(found_in)}" for value, found_in in fact.values.items()),
                    icon=":material/warning:")
        checks = fact_checks(details, company_link, fca_frn)
        # Plain tables wrap long text, so every column fits the page (a dataframe keeps each cell on one line)
        fit_table([{
            "Fact": c.fact,
            "Extracted": c.extracted or "—",
            "Found in": ", ".join(c.found_in) or "—",
            "Across documents": with_icon(STATUS_ICON[Status.PRESENT] if c.consistent else STATUS_ICON[Status.UNCLEAR],
                                          c.cross_check) if c.found_in else "—",
            "External verification": with_icon(STATUS_ICON[Status.PRESENT] if c.externally_verified
                                               else ":gray[:material/radio_button_unchecked:]", c.external),
            "Assessment": c.assessment,
        } for c in checks])
        named = people(details)
        if named:
            st.markdown("**People named**")
            fit_table([{"Name": name, "Roles": ", ".join(roles), "Found in": ", ".join(found_in)}
                       for name, roles, found_in in named])
        owned = owners(details)
        if owned:
            st.markdown("**Ownership**")
            fit_table([{
                "Owner": name,
                "Share": " / ".join(shares),
                "Found in": "; ".join(f"{share}: {', '.join(found_in)}" if len(shares) > 1 else ", ".join(found_in)
                                      for share, found_in in shares.items()),
                "Check": "Documents disagree" if len(shares) > 1 else "",
            } for name, shares in owned])



if screen == "documents":
    with tabs[1]:
        with st.container(border=True):
            st.subheader(":material/plagiarism: Check what each document is")
            if "identification" not in st.session_state:  # identify straight away when this screen opens
                with st.spinner(f"Clario is reading the {len(documents)} documents..."):
                    try:
                        st.session_state.identification = identify_documents(
                            documents, saved_answer=saved_answers.get("labels"))
                        found = st.session_state.identification
                        log_event(audit_path, "Clario", f"Identified {len(found.labels)} documents"
                                  + ("" if found.replayed else f" (AI usage ${found.cost_usd:.3f})"))
                    except (ExtractionFailed, UnsupportedFile) as error:
                        st.error(f"Could not identify the documents: {error}", icon=":material/error:")
                        st.button("Try again", icon=":material/refresh:")
            if "identification" in st.session_state:
                identification = st.session_state.identification
                # Your corrections, if you made any; after documents are added, the ones you made before carry over
                corrected = st.session_state.get("label_corrections", {})
                shown = st.session_state.get("labels") or [corrected.get(label.name, label)
                                                           for label in identification.labels]
                description_of = {d.name: d.description for d in documents}
                st.caption("Correct any document type that is wrong (the checks use these) and add comments. Open "
                           "a file's **Details** to see why Clario AI chose its type.")
                comments_before = st.session_state.get("label_comments", {})
                claude_types = {label.name: label.document_type for label in identification.labels}
                confirmed, comments = [], {}
                for number, label in enumerate(shown):
                    # One card per document: its type, comments and details together
                    with st.container(border=True):
                        with st.container(horizontal=True, vertical_alignment="center"):
                            st.markdown(f":material/description: **{label.name}**", width="stretch")
                            shown_file = next((d for d in documents if d.name == label.name), None)
                            if shown_file and st.button("View", icon=":material/visibility:",
                                                        key=f"view_doc_{pack_key}_{number}"):
                                view_document(shown_file.name, shown_file.data, shown_file.media_type)
                        type_side, comment_side = st.columns([2, 3])
                        chosen_type = type_side.selectbox(
                            "Document type", list(DOCUMENT_TYPES.values()),
                            index=list(DOCUMENT_TYPES).index(label.document_type), key=f"type_{pack_key}_{number}")
                        type_changed = TYPE_KEY[chosen_type] != claude_types[label.name]
                        comment = comment_side.text_input(
                            "Comments (required: you changed the type)" if type_changed else "Comments",
                            value=comments_before.get(label.name, ""), key=f"label_comment_{pack_key}_{number}",
                            placeholder="Why did you change the document type?" if type_changed
                            else "Optional comments on this document")
                        with st.expander(f"Details for {label.name}", icon=":material/info:"):
                            st.markdown(f"**Why Clario AI chose this type:** "
                                        f"{product_voice(label.reason) or 'No reason given.'}")
                            st.markdown(f"**Your description:** {description_of.get(label.name) or 'None given'}")
                            found = identification.details.get(label.name)
                            if found and not found.empty:
                                st.markdown("**What it shows:**\n" + "\n".join(f"- {line}"
                                                                                for line in detail_lines(found)))
                            elif identification.extracted:
                                st.caption("No company details were found in this document.")
                    confirmed.append(DocumentLabel(label.name, TYPE_KEY[chosen_type], label.reason))
                    if comment.strip():
                        comments[label.name] = comment.strip()

        if "identification" in st.session_state:
            show_key_facts(st.session_state.identification)
        def save_labels(quiet: bool = False) -> bool:
            """Keep the document types and comments, and record what changed in the audit log. A document type
            changed from Claude's needs a comment; if one is missing nothing is saved."""
            missing = [label.name for label in confirmed
                       if label.document_type != claude_types[label.name] and not comments.get(label.name)]
            if missing:
                if not quiet:
                    st.error("Add a comment for " + ", ".join(missing) + ": you changed the document type from "
                             "the one Clario AI suggested.", icon=":material/error:")
                return False
            before = {label.name: label for label in shown}
            who = st.session_state.get("last_reviewer", "")
            for label in confirmed:
                if label.document_type != before[label.name].document_type:
                    log_event(audit_path, who, f"Document type of {label.name}: {before[label.name].type_label} → "
                              f"{label.type_label}")
                if comments.get(label.name, "") != comments_before.get(label.name, ""):
                    log_event(audit_path, who, f'Comment on {label.name}: "{comments.get(label.name, "")}"')
            remember(labels=confirmed, label_comments=comments)
            return True

        navigation("Next", "identification" in st.session_state, save=save_labels)
        st.caption("Next: Clario suggests the industry and an initial risk rating.")
        st.stop()

# After a refresh, a later tab reloads the earlier tabs' results from their saved answers (free), so it opens directly
LATER_SCREENS = ("assess", "results", "monitoring")
if screen in LATER_SCREENS and "identification" not in st.session_state and st.session_state.get("labels"):
    restored = replay_only(lambda: identify_documents(documents, saved_answer=saved_answers.get("labels"),
                                                      client=ReplayOnly()))
    if restored:
        st.session_state.identification = restored

confirmed = st.session_state.get("labels") or []
identification = st.session_state.get("identification")
if not confirmed or identification is None:
    needs_first(screen, "documents")

# --- Screen 3: industry and initial risk rating, which together pick the checklist ---

RATING_COLOURS = {"Low": "green", "Medium": "orange", "High": "red", NOT_ENOUGH: "gray"}
LEVEL_MEANING = {
    "Low": "**Low risk: simplified due diligence.** Lighter identity checks and purpose-only business checks; no "
           "source of funds; review every 3 years.",
    "Medium": "**Medium risk: standard due diligence.** The full standard checklist for the industry.",
    "High": "**High risk: enhanced due diligence.** The standard checks plus the owners' source of wealth, two "
            "independent identity sources, documented source of funds, enhanced adverse media and closer "
            "monitoring; review every year.",
}


@st.cache_data
def checklist_size(key: str) -> int:
    return len(load_checks(CHECKLISTS[key][1]))

decision_path = case_file(cycle_review_key, "risk-decision")
links_key = (tuple(confirmed), company_link.strip(), website.strip(), fca_frn.strip())
if st.session_state.get("industry") and st.session_state.industry[0] != links_key:
    st.session_state.pop("industry")  # documents, labels or links changed
    st.session_state.pop("choice", None)
if screen in ("results", "monitoring") and "industry" not in st.session_state and st.session_state.get("choice"):
    restored_sources, _ = fetch_links(company_link, website, fca_frn)
    restored = replay_only(lambda: suggest_industry(documents, confirmed, restored_sources,
                                                    saved_answer=saved_answers.get("industry"), client=ReplayOnly()))
    if restored:
        st.session_state.industry = (links_key, restored)

if screen == "assess":
    with tabs[2]:
        sources, link_warnings = fetch_links(company_link, website, fca_frn)
        for warning in link_warnings:
            st.warning(warning, icon=":material/warning:")
        if "industry" not in st.session_state:  # both suggestions start straight away when this screen opens
            with st.spinner("Clario is reading the questionnaire, the registers and the website to work out the "
                            "industry..."):
                try:
                    st.session_state.industry = (links_key, suggest_industry(
                        documents, confirmed, sources, saved_answer=saved_answers.get("industry")))
                    suggested = st.session_state.industry[1]
                    log_event(audit_path, "Clario", f"Suggested the industry: {suggested.industry_label}"
                              + ("" if suggested.replayed else f" (AI usage ${suggested.cost_usd:.3f})"))
                except (ExtractionFailed, UnsupportedFile) as error:
                    st.error(f"Could not suggest the industry: {error}", icon=":material/error:")
                    st.button("Try again", icon=":material/refresh:")
                    navigation()
                    st.stop()
        suggestion = st.session_state.industry[1]
        risk_key = (pack_key, tuple(confirmed), suggestion.industry, tuple(sources))
        if st.session_state.get("risk", (None,))[0] != risk_key:
            with st.spinner("Clario is rating the risk from the ownership and business documents, the registers and the "
                            "website..."):
                try:
                    st.session_state.risk = (risk_key, suggest_risk(
                        documents, confirmed, INDUSTRIES[suggestion.industry], sources,
                        saved_answer=saved_answers.get("risk"),
                        update_saved=source != "Sample pack"))  # the sample's free demo answer is never replaced
                    rated = st.session_state.risk[1]
                    log_event(audit_path, "Clario", f"Rated the risk: {rated.overall} ({rated.why})"
                              + ("" if rated.replayed else f" (AI usage ${rated.cost_usd:.3f})"))
                except (ExtractionFailed, UnsupportedFile) as error:
                    st.error(f"Could not suggest a risk rating: {error}", icon=":material/error:")
                    st.button("Try again", icon=":material/refresh:")
                    navigation()
                    st.stop()
        risk = st.session_state.risk[1]
        decision = load_risk_decision(decision_path)
        stated_industry = saved.get("stated_industry", "")
        chosen_industry = st.session_state.get("choice", (stated_industry or suggestion.industry, None))[0]
        if chosen_industry not in INDUSTRIES:  # e.g. "Not enough information" in a review saved before it was removed
            chosen_industry = suggestion.industry

        st.subheader(":material/fact_check: Industry, risk rating and checklist")
        st.caption("Clario's suggestions are below. Change any of them if you disagree, and open **Why** to see Clario AI's "
                   "reasons and evidence.")

        # Risk rating on the left, industry and checklist on the right. The right-hand card is filled first because the
        # risk card needs to know which industry was chosen.
        risk_column, industry_column = st.columns([1, 2])
        # --- Industry and checklist, side by side in one box: only the industry can be overridden ---
        with industry_column.container(border=True):
            industry_side, checklist_side = st.columns(2)
            with industry_side:
                st.markdown("**:material/domain: Industry**")
                st.caption("Clario suggests")
                st.markdown(f"#### {suggestion.industry_label}")
                if suggestion.sources_agree == "no":
                    st.badge("Sources disagree", icon=":material/warning:", color="orange")
                if stated_industry in INDUSTRIES and stated_industry != suggestion.industry:
                    st.caption(f":material/info: You entered **{INDUSTRIES[stated_industry]}** on Details & "
                               "documents. Check which is right.")
                industry = INDUSTRY_KEY[st.selectbox(
                    "Override Industry", list(INDUSTRIES.values()), index=list(INDUSTRIES).index(chosen_industry),
                    key=f"industry_{hash(links_key)}", help="Change this if the suggested industry is wrong.",
                )]
                with st.expander("Why this industry?"):
                    st.markdown(suggestion.reason)
                    if suggestion.sources_agree == "no":
                        st.warning(f"**The sources disagree.** {suggestion.disagreement}", icon=":material/warning:")
                    else:
                        st.caption(SOURCES_AGREE[suggestion.sources_agree])
                    if suggestion.evidence:
                        st.markdown("**Evidence**\n" + "\n".join(f"- {quote}" for quote in suggestion.evidence))
            with checklist_side:
                st.markdown("**:material/checklist: Checklist**")
                checklist_slot = st.container()  # filled in below, once the risk rating is known

        # --- Risk rating ---
        with risk_column.container(border=True):
            st.markdown("**:material/speed: Risk rating**")
            st.caption("Clario suggests")
            st.markdown(f"#### :{RATING_COLOURS[risk.overall]}[{risk.overall}]")
            with st.container(horizontal=True):
                for found in risk.triggers:
                    st.badge(f"EDD trigger {found.trigger.id}", icon=":material/priority_high:", color="red")
                if risk.flagged:
                    st.badge(f"{len(risk.flagged)} factor(s) need evidence", icon=":material/help:", color="gray")
                if industry != suggestion.industry:
                    st.badge("Based on the suggested industry", icon=":material/info:", color="blue")
            final = st.segmented_control(
                "Override Rating", RATINGS, required=True, key=f"final_{pack_key}",
                default=decision.rating if decision else risk.overall,
                help="Keep Clario's suggestion or override it. An override needs a sign-off (below).")
            with st.expander("Why this rating?"):
                st.markdown(f"**{risk.why}.** Rules: any EDD trigger makes it High; otherwise the highest factor "
                            "wins; a factor without enough evidence counts as Medium.")
                if industry != suggestion.industry:
                    st.info(f"This rating was based on the suggested industry ({suggestion.industry_label}). You "
                            f"chose {INDUSTRIES[industry]}: review the rating and override it if needed.",
                            icon=":material/info:")
                for found in risk.triggers:
                    st.warning(f"**EDD trigger {found.trigger.id}: {found.trigger.text}** ({found.trigger.kind})  \n"
                               f"{found.reasons}" + "".join(f"  \n> {quote}" for quote in found.evidence),
                               icon=":material/priority_high:")
                for rated in risk.factors:
                    st.markdown(f"**{rated.factor.name}** :{RATING_COLOURS[rated.rating]}-badge[{rated.rating}]  \n"
                                f"{rated.reasons}")
                    if rated.evidence:
                        st.caption("\n".join(f"- {quote}" for quote in rated.evidence))

        # The checklist follows the industry and the risk rating; it cannot be changed on its own
        checklist, written_for_industry = checklist_for(industry, final)
        with checklist_slot:
            st.caption("Set by the industry and risk rating")
            st.markdown(f"#### {CHECKLISTS[checklist][0]}")
            if not written_for_industry:
                st.badge("No checklist for this industry yet", icon=":material/info:", color="gray")
            with st.expander("Why this checklist?"):
                st.markdown(f"Set from the industry (**{INDUSTRIES[industry]}**) and the risk rating (**{final}**).  \n"
                            f"{LEVEL_MEANING[final]}")
                st.caption(f"{checklist_size(checklist)} checks.")
                if not written_for_industry:
                    st.caption("There is no checklist written for this industry yet, so the fintech one is used.")

        # --- Sign-off: only when the analyst overrides Clario's suggested rating ---
        reason, reviewer, evidence_link, evidence = "", "", "", None
        if final != risk.overall:
            overridden_before = decision and decision.overridden
            with st.container(border=True):
                st.markdown("**:material/gavel: AML senior officer sign-off for the override**")
                st.caption(f":material/edit: You are overriding Clario's suggested rating ({risk.overall}) with {final}. "
                           "An AML senior officer must sign this off, with evidence of the sign-off.")
                reason = st.text_area("Reason", value=decision.reason if overridden_before else "",
                                      key=f"reason_{pack_key}", height=80)
                reviewer = st.text_input("AML senior officer", key=f"reviewer_{pack_key}",
                                         value=decision.reviewer if overridden_before else "",
                                         help="Name of the AML senior officer who signed off the override.")
                st.markdown("**Evidence of the sign-off** (a document, a link, or both)")
                with st.container(horizontal=True):
                    upload = None if is_demo() else st.file_uploader(
                        "Sign-off document", key=f"evidence_{pack_key}",
                        type=["pdf", "png", "jpg", "jpeg", "docx", "msg", "eml"],
                        help="For example the signed form, or the approval email saved as a PDF.")
                    evidence_link = st.text_input(
                        "Or a link to the folder where the evidence is saved", key=f"evidence_link_{pack_key}",
                        value=decision.evidence_link if overridden_before else "",
                        placeholder="e.g. https://yourfirm.sharepoint.com/sites/kyc/EXAMPLE-PAYMENTS")
                if upload:
                    evidence = (upload.name, upload.getvalue())
                elif overridden_before and decision.evidence_document and evidence_path(decision_path).exists():
                    with st.container(horizontal=True, vertical_alignment="center"):
                        st.caption(f":material/attach_file: On file: {decision.evidence_document}. Upload a new "
                                   "document to replace it.")
                        st.download_button("Download", evidence_path(decision_path).read_bytes(),
                                           file_name=decision.evidence_document, icon=":material/download:",
                                           key=f"evidence_download_{pack_key}")

        with st.container(horizontal=True):
            if st.button("Back", icon=":material/arrow_back:", key="back_assess"):
                go("documents")
            if st.button("Next", type="primary", icon=":material/arrow_forward:", key="next_assess"):
                try:
                    saved_decision = save_risk_decision(decision_path, final, risk.overall, reason, reviewer,
                                                        evidence_link=evidence_link, evidence=evidence)
                except ValueError as error:
                    st.error(str(error), icon=":material/error:")
                else:
                    before = (decision.rating, decision.reason, decision.reviewer, decision.evidence_link,
                              decision.evidence_document) if decision else None
                    after = (saved_decision.rating, saved_decision.reason, saved_decision.reviewer,
                             saved_decision.evidence_link, saved_decision.evidence_document)
                    if before != after:
                        if saved_decision.overridden:
                            evidence_given = " and ".join(e for e in (saved_decision.evidence_document,
                                                                      saved_decision.evidence_link) if e)
                            log_event(audit_path, saved_decision.reviewer,
                                      f"Overrode the risk rating {risk.overall} → {final}, signed off as AML senior "
                                      f"officer: {saved_decision.reason} (evidence: {evidence_given})")
                        else:
                            log_event(audit_path, st.session_state.get("last_reviewer", ""),
                                      f"Confirmed Clario's risk rating {final}")
                    if st.session_state.get("choice", (None, None)) != (industry, checklist):
                        log_event(audit_path, st.session_state.get("last_reviewer", ""),
                                  f"Industry {INDUSTRIES[industry]}"
                                  + (f" (Clario suggested {suggestion.industry_label})" if industry != suggestion.industry
                                     else "") + f"; checklist {CHECKLISTS[checklist][0]}")
                    remember(choice=(industry, checklist))
                    go("results")
        st.caption("Next saves your choices and runs the KYC checks against the checklist.")
        st.stop()

decision = load_risk_decision(decision_path)
if "industry" not in st.session_state or not st.session_state.get("choice", (None, None))[1] or decision is None:
    needs_first(screen, "assess")
suggestion = st.session_state.industry[1]
industry, checklist = st.session_state.choice

with open_tab:  # Evidence review, or Ongoing monitoring: both work from the checked results
    # Results no longer match if the labels, the checklist or the review cycle changed
    if st.session_state.get("assessment") and st.session_state.assessment[0] != (confirmed, checklist, cycle):
        st.session_state.pop("assessment")
    # A periodic review checks the documents again as at the date it started, so out-of-date evidence is flagged
    review_date = cycle_started_on(review_key) if cycle > 1 else None

    # --- Screen 5: results. The checks run as this screen opens, then the results appear ---

    if "assessment" not in st.session_state:
        replay_sample = source == "Sample pack" and checklist == SAMPLE_CHECKLIST
        if review_date:
            answer_path = assessment_answer_path(review_key, cycle)
        else:
            answer_path = saved_answers.get("assessment") if replay_sample or source != "Sample pack" else None
        sources, _ = fetch_links(company_link, website, fca_frn)
        with st.spinner(f"Clario is checking the {len(documents)} documents against every item on the "
                        f"{CHECKLISTS[checklist][0]} checklist. This can take a minute..."):
            try:
                st.session_state.assessment = ((confirmed, checklist, cycle), assess_pack(
                    documents, confirmed, sources, checklist=CHECKLISTS[checklist][1], saved_answer=answer_path,
                    review_date=review_date,
                ))
                checked = st.session_state.assessment[1]
                log_event(audit_path, "Clario", f"Checked {len(documents)} documents against the "
                          f"{CHECKLISTS[checklist][0]} checklist"
                          + (f" as at {review_date:%d %b %Y} for {cycle_name(cycle).lower()}" if review_date else "")
                          + ("" if checked.replayed else f" (AI usage ${checked.cost_usd:.3f})"))
                st.rerun()  # once, so the workspace summary at the top shows the results (saved, so free)
            except ExtractionFailed as error:
                st.error(f"Could not run the checks: {error}", icon=":material/error:")
                st.button("Try again", icon=":material/refresh:")
                navigation()
                st.stop()
    original = st.session_state.assessment[1]

    # The analyst's saved changes for this set of documents and checklist
    review_path = case_file(cycle_review_key, checklist)
    overrides = load_overrides(review_path)
    # The legal entity name rule on check 1.1, then the analyst's changes, which always have the final say
    named = apply_entity_name(original, entity_name, parse_company_number(company_link), lookup=cached_company)
    result = apply_overrides(named, overrides)

    approval_path = case_file(cycle_review_key, "final-approval")
    approval = load_approval(approval_path)

    # Evidence review covers sections 1 to 6. Section 7 (risk rating and escalation) is covered by the risk assessment,
    # the final approval and the audit log. Section 8 (monitoring set-up: review date, early-review triggers, record
    # keeping) is firm policy outside Clario; Clario sets the next review date itself when a review is approved.
    RISK_SECTION, ONGOING_SECTION = "7.", "8."
    review_outcomes = [o for o in result.outcomes if not o.check.section.startswith((RISK_SECTION, ONGOING_SECTION))]
    review_ids = {o.check.id for o in review_outcomes}
    submission = load_submission(review_key, cycle)

    def document_list() -> list[dict]:
        return ([{"name": d.name, "description": d.description, "supports": "Original document"}
                 for d in original_documents]
                + [{"name": r["name"], "description": r.get("description", ""), "supports": f"Check {r['check_id']}"}
                   for _, r in stored_supporting])

    def document_files() -> dict[str, UploadedDocument]:
        """Every document in the review, original and supporting, by name."""
        return {d.name: d for d in original_documents} | {d.name: d for d, _ in stored_supporting}

    def freeze_now(given: "FinalApproval"):
        """Freeze the checklist as it stands, at approval, with a copy of every document used."""
        return freeze(review_key, cycle, result, given.approver, given.approved_on, given.note, industry, checklist,
                      asdict(decision), document_list(), files=document_files())

    snapshot = load_snapshot(review_key, cycle) if approval else None
    if approval and not snapshot:  # approved before checklists were frozen: freeze it as it stands now
        snapshot = freeze_now(approval)
    history = approved_snapshots(review_key)  # every approved cycle, most recent first

    def frozen_line(line) -> None:
        status = Status(line.status)
        if line.before_review:  # the analyst (or a supporting document) changed Clario AI's answer
            original, _, found = line.before_review.partition("): ")
            original_status = original.split(" (")[0]
            changed = f"Status changed from {original_status} to {status.value} ({product_voice(line.decided_by)})"
        else:
            found, changed = line.finding, ""
        with st.container(border=True):
            text_side, status_side = st.columns([5, 2], vertical_alignment="center")
            text_side.markdown(f"**{line.id}** {line.check}")
            status_side.markdown(STATUS_BADGE[status])
            st.caption(f":material/verified: Validated by {line.validated_by}" if line.validated_by
                       else ":material/remove_done: Not validated")
            clario_side, analyst_side = st.columns(2)
            with clario_side.container(border=True, height="stretch"):
                st.markdown("**:material/smart_toy: Clario AI found**")
                st.markdown(product_voice(found) or "_Nothing recorded._")
                if changed:
                    st.caption(f":material/edit: {changed}")
            with analyst_side.container(border=True, height="stretch"):
                st.markdown("**:material/person: Analyst comment**")
                st.markdown(line.comment or "_No comment._")
            if line.evidence:
                with st.expander(f"Evidence ({len(line.evidence)})", icon=":material/format_quote:"):
                    st.markdown("\n".join(f"- {quote}" for quote in line.evidence))

    def show_frozen(frozen, key: str) -> None:
        """A checklist exactly as it was approved, read-only: for each line, what Clario AI found and wrote at the
        time, and the analyst's comment."""
        lines_shown = [line for line in frozen.lines if not line.section.startswith((RISK_SECTION, ONGOING_SECTION))]
        for section, section_lines in groupby(lines_shown, key=lambda line: line.section):
            section_lines = list(section_lines)
            present = sum(line.status == Status.PRESENT.value for line in section_lines)
            with st.expander(f"{section} · {present} of {len(section_lines)} present"):
                for line in section_lines:
                    frozen_line(line)

        if frozen.documents:
            if not all(d.get("sha256") for d in frozen.documents):  # approved before copies were kept
                frozen = attach_documents(review_key, frozen.cycle, document_files()) or frozen
            with st.expander(f"Documents at approval ({len(frozen.documents)})", icon=":material/folder_open:"):
                st.caption("Each document exactly as it was when the review was approved. Later uploads or deletions "
                           "do not change these copies.")
                for number, document in enumerate(frozen.documents):
                    data = approved_document(review_key, frozen.cycle, document.get("sha256", ""))
                    name_side, view_side, button_side = st.columns([5, 1, 1], vertical_alignment="center")
                    name_side.markdown(f":material/description: **{document['name']}**  \n"
                                       + " · ".join(filter(None, [document.get("supports"),
                                                                  document.get("description")])))
                    if data:
                        if view_side.button("View", icon=":material/visibility:", key=f"view_approved_{key}_{number}",
                                            width="stretch"):
                            view_document(document["name"], data, document.get("media_type", "application/pdf"))
                        button_side.download_button(
                            "Download", data, file_name=document["name"], key=f"approved_doc_{key}_{number}",
                            mime=document.get("media_type", "application/pdf"), icon=":material/download:",
                            width="stretch")
                    else:
                        button_side.caption("No copy kept")

    def withdraw(who: str) -> None:
        withdraw_approval(approval_path)
        remove_snapshot(review_key, cycle)
        log_event(audit_path, who, f"Withdrew the approval given by {approval.approver} on {approval.approved_on}; "
                  "the checklist can be changed again")

    if screen == "results" and snapshot:  # approved: the checklist is frozen
        st.header("Results")
        with st.container(border=True, horizontal=True, vertical_alignment="center"):
            with st.container():
                st.caption("Checklist")
                st.markdown(f"#### {CHECKLISTS[checklist][0]}")
                st.caption(f"{cycle_review_id(review_key, cycle)} · {cycle_name(cycle)} · Industry: "
                           f"{INDUSTRIES[industry]}")
            with st.container():
                st.caption("Final approval")
                st.markdown("#### :green[Approved]")
                st.caption(f"By {approval.approver} on {approval.approved_on}")
        st.info(f"**Frozen at approval.** This is the checklist exactly as it stood when {snapshot.approved_by} "
                f"approved it on {snapshot.approved_on}, and it can no longer be changed. The next review starts from "
                "it: open **Ongoing monitoring** to start a periodic review.", icon=":material/lock:")
        st.subheader("Every check, by section")
        show_frozen(snapshot, "current")
        with st.container(border=True):
            st.subheader(":material/verified: Final approval")
            st.success(f"**Approved by {approval.approver}** on {approval.approved_on}"
                       + (f": {approval.note}" if approval.note else "."), icon=":material/verified:")
            who = st.text_input("Your name", value=st.session_state.get("last_reviewer", ""), key="withdraw_who",
                                width=300)
            st.button("Withdraw approval", icon=":material/undo:", on_click=withdraw, args=(who,),
                      disabled=not who.strip(), help="Unfreezes the checklist so it can be changed and approved again.")
        navigation("Ongoing monitoring")
        st.stop()

    if screen == "results":
        st.header("Results")
        with st.container(border=True, horizontal=True, vertical_alignment="center"):
            with st.container():
                st.caption("Checklist")
                st.markdown(f"#### {CHECKLISTS[checklist][0]}")
                st.caption(f"{len(result.outcomes)} checks · Industry: {INDUSTRIES[industry]}")
                if decision.overridden:
                    st.caption(f"Risk rating overridden from {decision.suggested}; signed off by {decision.reviewer}, AML "
                               "senior officer")
                if cycle > 1:
                    st.caption(cycle_name(cycle))
            with st.container():
                st.caption("Final approval")
                if approval:
                    st.markdown(f"#### :green[Approved]")
                    st.caption(f"By {approval.approver} on {approval.approved_on}")
                else:
                    st.markdown("#### :orange[Submitted]" if submission else "#### :orange[Awaiting]")
                    st.caption(f"Submitted by {submission['by']} on {submission['on']}" if submission
                               else "Submit for approval at the end of this page")
        if cycle > 1 and history:
            with st.container(border=True):
                st.markdown(f"**:material/autorenew: {cycle_name(cycle)}**: the checklist was run again as at "
                            f"{review_date:%d %b %Y}, so evidence that is out of date is flagged. Each line shows what "
                            f"was approved on {history[0].approved_on} by {history[0].approved_by}; validate every line "
                            "again, then submit for approval.")
        # --- What to chase: requests to the client and checks on public registers ---

        left, right = st.columns(2)
        for column, title, gaps, empty, to_do in [
            (left, "Request from client", result.request_from_client(), "Nothing to request.", "to request"),
            (right, "Check on public registers", result.check_on_registers(), "Nothing to check.", "to check"),
        ]:
            # One box each: an action-required badge and title, with the items in a fold-out inside
            items = f"{len(gaps)} item{'s' if len(gaps) != 1 else ''}"
            with column.container(border=True):
                if gaps:
                    st.badge("Action required", icon=":material/priority_high:", color="orange")
                    st.markdown(f"**{title}** · {items} {to_do}")
                    with st.expander(f"Show the {items}", icon=":material/list:"):
                        for outcome in gaps:
                            st.markdown(f"**{outcome.check.id} · {outcome.check.evidence_source}**  \n"
                                        f"{outcome.finding}")
                else:
                    st.badge("Complete", icon=":material/check:", color="green")
                    st.markdown(f"**{title}** · {empty}")

        # Status tiles: click View to show only the lines with that status
        line_filter = st.session_state.get("line_filter")
        with st.container(horizontal=True, wrap=True):
            for status, short, help_text in [
                (Status.PRESENT, "Evidence in place", "The evidence is there and consistent"),
                (Status.MISSING, "Not provided", "Not provided by the client"),
                (Status.UNCLEAR, "Needs clarifying", "Incomplete, out of date or inconsistent"),
                (Status.NEEDS_HUMAN_REVIEW, "Analyst judgement", "A judgement call for an analyst"),
                (Status.NOT_STARTED, "Done outside Clario", "Screening and analyst decisions, done outside Clario"),
            ]:
                with st.container(border=True, width=228, height=180, vertical_alignment="distribute"):
                    with st.container(gap=None):
                        st.markdown(STATUS_BADGE[status])
                        st.header(str(sum(o.status is status for o in review_outcomes)), anchor=False)
                        st.caption(short, help=help_text)
                    showing = line_filter == status.value
                    st.button("Showing" if showing else "View", key=f"line_filter_{status.name}", type="tertiary",
                              icon=":material/check:" if showing else ":material/arrow_forward:", disabled=showing,
                              on_click=st.session_state.update, kwargs={"line_filter": status.value})

        # --- Every check, validated line by line ---

        st.subheader("Every check, by section")
        st.caption(
            "For each line: tick **Validated** once you have checked it, change the **Status** if you disagree (a "
            "**comment** is then required), and open **Details** for the finding, Clario AI's view, who decided and the "
            "evidence, or to upload supporting documents. Then click **Save review**."
        )
        validated_count = sum(bool(o.validated_by) for o in review_outcomes)
        st.progress(validated_count / len(review_outcomes),
                    text=f"{validated_count} of {len(review_outcomes)} lines validated")

    supporting_by_check, supporting_documents = {}, {}
    if st.session_state.get("case_id"):
        for document, record in load_supporting(st.session_state.case_id):
            supporting_by_check.setdefault(record["check_id"], []).append(record)
            supporting_documents[document.fingerprint] = (document, record)
    in_this_run = {d.fingerprint for d in documents}
    section_reads = st.session_state.setdefault("section_reads", {})  # section -> documents its re-run has read
    not_yet_read = [r for _, r in supporting_documents.values() if r["sha256"] not in in_this_run]
    if not_yet_read and screen == "results":
        with st.container(border=True):
            st.info(f"{len(not_yet_read)} supporting document(s) added since the checks ran: "
                    + ", ".join(r["name"] for r in not_yet_read) + ". Re-run the section they belong to (button in each "
                    "section), or re-run all the checks, so Clario reads them with the rest of the documents.",
                    icon=":material/attach_file:")
            if st.button("Re-run all the checks with the new documents", icon=":material/refresh:",
                         disabled=is_demo(), help=DEMO_NOTE if is_demo() else None):
                st.session_state.entity = {**saved, "supporting": [d for d, _ in supporting_documents.values()]}
                go("documents")
            st.caption("Re-running everything reads every document again, with the industry and risk rating. Your "
                       "line reviews are kept.")


    def rerun_section(section: str, check_ids: set[str], unread: list[tuple[UploadedDocument, dict]]) -> None:
        """Re-check one section with every document, including supporting ones Claude has not read yet."""
        extra_docs = [document for document, _ in unread]
        extra_labels = [DocumentLabel(document.name, "other", f"Supporting document added for check {record['check_id']}")
                        for document, record in unread]
        sources, _ = fetch_links(company_link, website, fca_frn)
        with st.spinner(f"Clario is re-checking {section} with {len(documents) + len(extra_docs)} documents..."):
            partial = assess_pack(documents + extra_docs, confirmed + extra_labels, sources,
                                  checklist=CHECKLISTS[checklist][1], only=check_ids, review_date=review_date)
        new_lines = {o.check.id: o for o in partial.outcomes}
        key, current = st.session_state.assessment
        st.session_state.assessment = (key, replace(
            current, outcomes=[new_lines.get(o.check.id, o) for o in current.outcomes], replayed=False,
            input_tokens=current.input_tokens + partial.input_tokens,
            output_tokens=current.output_tokens + partial.output_tokens))
        section_reads[section] = section_reads.get(section, set()) | {d.fingerprint for d in extra_docs}
        log_event(audit_path, st.session_state.get("last_reviewer", ""),
                  "Re-ran the section with " + ", ".join(d.name for d in extra_docs), section)


    if screen == "results":  # the checklist is only on Evidence review
        reviewer = st.text_input("Reviewer", value=st.session_state.get("last_reviewer", ""), width=300,
                                 help="Your name, recorded against every line you validate or change.")
    else:
        reviewer = st.session_state.get("last_reviewer", "")
    line_versions = st.session_state.setdefault("line_versions", {})  # a line's fields start fresh after it is saved
    unsaved_lines = st.session_state.setdefault("unsaved_lines", {})  # changes not saved yet, by check ID
    section_open = st.session_state.setdefault("section_open", {})  # which checklist sections the user opened


    def remember_section(section_key: str) -> None:
        section_open[section_key] = st.session_state[section_key]


    def is_changed(line) -> bool:
        o, status, validated, comment, uploads, _ = line
        return (status, validated, comment) != (o.status, bool(o.validated_by), o.reviewer_note) or bool(uploads)


    def save_lines(selected: list) -> list[str]:
        """Save these lines: status, tick and comment, then add any uploaded documents, which Claude reads against
        their line and can set to Present. Returns problems; nothing is saved if there are any."""
        touched = [(o.check.id, status, comment, validated) for o, status, validated, comment, _, _ in selected
                   if (status, validated, comment) != (o.status, bool(o.validated_by), o.reviewer_note)]
        uploads_for = [(o, comment, validated, upload, description)
                       for o, _, validated, comment, uploads, description in selected for upload in uploads]
        problems = save_line_reviews(review_path, named, touched, reviewer)
        if uploads_for and not st.session_state.get("case_id"):
            problems.append("Save the review (Next on the first screen) before adding supporting documents")
        if problems:
            return problems
        shown = {o.check.id: o for o, *_ in selected}
        for check_id, status, comment, validated in touched:
            o = shown[check_id]
            log_event(audit_path, reviewer, describe_line_change(o.status.value, status.value, bool(o.validated_by),
                                                                  validated, o.reviewer_note, comment), check_id)
        changed_by_you = {check_id for check_id, status, _, _ in touched if status is not shown[check_id].status}
        for o, comment, validated, upload, description in uploads_for:
            document = UploadedDocument(upload.name, upload.getvalue(), media_type_for(upload.name, upload.type))
            verdict = None
            if o.status is not Status.PRESENT:  # Claude reads it against this one line
                with st.spinner(f"Clario is reading {document.name} against check {o.check.id}..."):
                    try:
                        verdict = read_supporting_document(o.check, o.finding, document, description)
                    except (ExtractionFailed, UnsupportedFile) as error:
                        st.warning(f"{document.name} was added, but Clario could not read it ({error}).",
                                   icon=":material/warning:")
            add_supporting_document(st.session_state.case_id, document, o.check.id, reviewer,
                                    verdict=verdict.label if verdict else "",
                                    verdict_finding=verdict.finding if verdict else "", description=description)
            log_event(audit_path, reviewer, f"Added supporting document {document.name}"
                      + (f' ("{description.strip()}")' if description.strip() else ""), o.check.id)
            if verdict and verdict.satisfies == "yes" and o.check.id not in changed_by_you:
                explanation = verdict.finding + "".join(f" {quote}" for quote in verdict.evidence[:1])
                note = (f"{comment.strip()} (Clario AI, from {document.name}: {explanation})" if comment.strip()
                        else f"Clario AI, from {document.name}: {explanation}")
                save_override(review_path, named, o.check.id, Status.PRESENT, note, reviewer or "Clario",
                              validated=validated, via=document.name)
            if verdict:
                log_event(audit_path, "Clario AI", f"Read {document.name}: {verdict.label}"
                          + (f" → status {o.status.value} → Present" if verdict.satisfies == "yes"
                             and o.check.id not in changed_by_you else ""), o.check.id)
        if reviewer.strip():
            st.session_state.last_reviewer = reviewer.strip()
        if submission and any(o.check.id in review_ids for o, *_ in selected):
            withdraw_submission(review_key, cycle)
            log_event(audit_path, reviewer, "Withdrew the submission for approval because the checklist changed; "
                      "submit it again when it is ready")
        for o, *_ in selected:
            line_versions[o.check.id] = line_versions.get(o.check.id, 0) + 1
        return []


    lines = []  # (outcome, status, validated, comment, uploads, description) as shown on screen
    earlier = load_snapshot(review_key, cycle - 1) if cycle > 1 else None
    last_approved = {line.id: line for line in earlier.lines} if earlier else {}
    entered_number = parse_company_number(company_link) or company_link.strip()
    found_in_documents = identification.details if identification and identification.extracted else {}


    def line_details(o) -> tuple[list[Row], list[str], list[tuple[str, str, str]]]:
        """What one line rests on: from the documents, the public registers and website, and the analyst."""
        documents_said, registers_said = from_documents_and_registers(
            o.check.id, o.check.section, named.line_facts(o.check.id), found_in_documents, o.evidence,
            {d.name for d in documents})
        analyst_said = provided_by_analyst(o.check.id, o.check.evidence_source, entity_name, entered_number, fca_frn,
                                           website, supporting_by_check.get(o.check.id, []))
        return documents_said, registers_said, analyst_said


    def render_line(o) -> None:
        """One checklist line: status, tick, comment and Save, with Details and a supporting document."""
        key = f"{review_path.stem}_{o.check.id}_{line_versions.get(o.check.id, 0)}"
        widgets = {"status": f"status_{key}", "validated": f"validated_{key}", "comment": f"comment_{key}"}
        pending = unsaved_lines.get(o.check.id)
        if pending and set(pending["values"]) == set(widgets.values()):
            for widget, value in pending["values"].items():
                st.session_state.setdefault(widget, value)  # an unsaved change made before the line was hidden

        def starting(widget: str, value) -> dict:
            """The saved value, unless the field already holds one (then Streamlit keeps that)."""
            return {} if widgets[widget] in st.session_state else value

        with st.container(border=True):
            text_side, status_side, tick_side = st.columns([5, 2, 1], vertical_alignment="center")
            text_side.markdown(f"**{o.check.id}** {o.check.check}")
            if o.check.id in last_approved:
                before = last_approved[o.check.id]
                text_side.caption(f":material/history: Last approved on {earlier.approved_on}: **{before.status}**"
                                  + (f" · {before.comment}" if before.comment else ""))
            status = STATUS_FROM_TEXT[status_side.selectbox(
                "Status", list(STATUS_TEXT.values()), key=widgets["status"], label_visibility="collapsed",
                **starting("status", {"index": list(STATUS_TEXT).index(o.status)}))]
            validated = tick_side.checkbox("Validated", key=widgets["validated"],
                                           **starting("validated", {"value": bool(o.validated_by)}))
            comment_side, line_save_side = st.columns([6, 1], vertical_alignment="center")
            comment = comment_side.text_input(
                "Comment", key=widgets["comment"], label_visibility="collapsed",
                placeholder="Comment (required if you change the status)",
                **starting("comment", {"value": o.reviewer_note}))
            with st.expander("Details"):
                documents_said, registers_said, analyst_said = line_details(o)
                st.markdown("**:material/gavel: Clario's decision**")
                st.markdown(f"- **Finding:** {o.finding}"
                            + (f"\n- **Clario AI's view:** {product_voice(o.claude_finding)}" if o.claude_finding
                               else "")
                            + f"\n- **Decided by:** {product_voice(o.decided_by)}"
                            + (f" · **Validated by:** {o.validated_by}" if o.validated_by else "")
                            + (f"\n- **Before the change:** {product_voice(o.before_review)}" if o.before_review
                               else ""))
                # Everything the line used, in its own fold-out, minimised to start with: the decision comes first
                used = len(documents_said) + len(registers_said) + len(analyst_said)
                with st.expander(f"**Information used** ({used})", icon=":material/fact_check:", expanded=False,
                                 key=f"information_{key}"):
                    st.markdown("**:material/description: Extracted from the documents**")
                    if not documents_said:
                        st.caption("Nothing was found in the documents for this line.")
                    for number, (label, value, sources, disagree) in enumerate(documents_said):
                        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
                            shown = f"“{as_written(value)}”" if label == "Quoted" else f"**{as_written(value)}**"
                            st.markdown((":orange[:material/warning:] " if disagree else "")
                                        + f"{as_written(label)}: {shown}"
                                        + (" · :orange[documents disagree]" if disagree else ""), width="stretch")
                            count = len({without_page(source) for source in sources})
                            with st.popover(f"{count} document{'s' if count > 1 else ''}", type="tertiary",
                                            icon=":material/find_in_page:", help="Where this was found",
                                            key=f"where_{key}_{number}"):
                                st.markdown("\n".join(f"- {as_written(source)}" for source in sources))
                    if registers_said:
                        st.markdown("**:material/account_balance: From the public registers and website**")
                        st.markdown("\n".join(f"- {as_written(said)}" for said in registers_said))
                    if analyst_said:
                        st.markdown("**:material/person: Provided by the analyst**")
                        st.markdown("\n".join(f"- {label}: **{as_written(value)}**"
                                               + (f" {as_written(note)}" if note else "")
                                               for label, value, note in analyst_said))
            # Add a supporting document: upload, describe it and save, in a fold-out section
            uploads, description, upload_save = [], "", False  # nothing to add in the public demo
            with st.expander("Upload supporting document", icon=":material/attach_file:"):
                if is_demo():
                    st.caption(DEMO_NOTE)
                else:
                    uploads = st.file_uploader(
                        "Document", type=UPLOAD_TYPES, accept_multiple_files=True, key=f"upload_{key}",
                        help="Added to the review's document store when you save this line.")
                    description = st.text_input(
                        "What does this document show? (optional)", key=f"description_{key}",
                        placeholder="e.g. Updated register of members, dated 20 Oct 2026",
                        help="Clario AI reads this with the document to understand what it is for.")
                    if uploads and o.status is not Status.PRESENT:
                        st.caption(":material/smart_toy: When you save, Clario reads the document against this "
                                   "check and sets the line to Present if it provides the evidence.")
                    upload_save = st.button("Save", icon=":material/save:", key=f"save_upload_{key}",
                                            disabled=not uploads, help="Add the document and save this line.")
            line = (o, status, validated, comment or "", uploads or [], description or "")
            lines.append(line)
            if is_changed(line):
                what = [f"status changed to {status.value}"] if status is not o.status else []
                if validated != bool(o.validated_by):
                    what.append("Validated ticked" if validated else "Validated unticked")
                if (comment or "") != o.reviewer_note:
                    what.append("comment edited")
                if uploads:
                    what.append("document attached (add it again if you leave)")
                unsaved_lines[o.check.id] = {
                    "tab": TAB_NAMES[SCREENS.index(screen)], "section": o.check.section,
                    "line": f"{o.check.id} {o.check.check}", "what": ", ".join(what),
                    "values": {widgets["status"]: STATUS_TEXT[status], widgets["validated"]: validated,
                               widgets["comment"]: comment or ""}}
            else:
                unsaved_lines.pop(o.check.id, None)
            line_save = line_save_side.button("Save", icon=":material/save:", key=f"save_{key}",
                                              disabled=not is_changed(line), help="Save this line now.",
                                              width="stretch")
            if line_save or upload_save:
                problems = save_lines([line])
                if problems:
                    st.error("Not saved:\n" + "\n".join(f"- {problem}" for problem in problems),
                             icon=":material/error:")
                else:
                    st.rerun()



    if screen == "monitoring":
        st.header("Ongoing monitoring")
        if not history:
            st.info("Opens once the review is approved: the next review date, periodic reviews and the review "
                    "history.", icon=":material/info:")
            if st.button("Go to Evidence review", icon=":material/arrow_back:"):
                go("results")
            st.stop()
        last = history[0]
        rating = last.risk.get("rating", "")
        due = next_review_date(last.approved_on, rating)
        with st.container(horizontal=True):
            st.metric("Next review due", f"{due:%d %b %Y}", border=True,
                      help=f"{REVIEW_YEARS.get(rating, 1)} year(s) after approval for a {rating} risk client "
                           "(risk methodology)")
            st.metric("Risk rating", rating or "Not rated", border=True)
            st.metric("Last approved", f"{date.fromisoformat(last.approved_on):%d %b %Y}", border=True,
                      help=f"{cycle_name(last.cycle)}, approved by {last.approved_by}")

        with st.container(border=True):
            st.subheader(":material/autorenew: Periodic review")
            if approval:
                st.caption(f"Clario runs the checklist again as at today and flags any evidence that is out of date "
                           f"and no longer valid. Every line starts without **Validated**, so you check each one again, "
                           f"with what was approved on {last.approved_on} shown beside it, add any new documents, then "
                           "submit it for approval. The documents, industry and risk rating carry over.")
                who = st.text_input("Your name", value=st.session_state.get("last_reviewer", ""), key="periodic_who",
                                    width=300)
                if is_demo():
                    st.caption(DEMO_NOTE)
                if st.button("Start periodic review", type="primary", icon=":material/play_arrow:",
                             disabled=not who.strip() or is_demo()):
                    new_cycle = start_periodic_review(review_key)
                    new_key = cycle_key(review_key, new_cycle)
                    copy_file(decision_path, case_file(new_key, "risk-decision"))
                    log_event(audit_path, who, f"Started {cycle_name(new_cycle).lower()}; the checklist runs again and "
                              "every line is to be validated again")
                    st.session_state.last_reviewer = who.strip()
                    st.session_state.pop("assessment", None)
                    go("results")
            else:
                st.info(f"**{cycle_name(cycle)}** is in progress. Validate every line in **Evidence review**, then "
                        "submit it for approval.", icon=":material/pending_actions:")
                if st.button("Go to Evidence review", icon=":material/arrow_forward:"):
                    go("results")

        with st.container(border=True):
            st.subheader(":material/history: Review history")
            st.caption("Each approved review, frozen as it stood at approval.")
            for past in history:
                with st.expander(f"{cycle_review_id(review_key, past.cycle)} · {cycle_name(past.cycle)} · approved "
                                 f"on {past.approved_on} by {past.approved_by} · {past.risk.get('rating', '')} risk"):
                    if past.note:
                        st.caption(f"Approval note: {past.note}")
                    show_frozen(past, f"history_{past.cycle}")
        navigation()
        st.stop()

    line_filter = st.session_state.get("line_filter")
    if line_filter:
        with st.container(horizontal=True, vertical_alignment="center"):
            matching = sum(o.status.value == line_filter for o in review_outcomes)
            st.caption(f":material/filter_alt: Showing the {matching} line(s) with status **{line_filter}**.",
                       width="stretch")
            st.button("Show all lines", icon=":material/filter_alt_off:", key="line_filter_clear",
                      on_click=st.session_state.pop, args=("line_filter", None))
    for section, outcomes in groupby(review_outcomes, key=lambda o: o.check.section):
        outcomes = list(outcomes)
        if line_filter:
            outcomes_shown = [o for o in outcomes if o.status.value == line_filter]
            if not outcomes_shown:
                continue  # nothing with this status in this section
        else:
            outcomes_shown = outcomes
        present = sum(o.status is Status.PRESENT for o in outcomes)
        open_issues = sum(o.status in (Status.MISSING, Status.UNCLEAR, Status.NEEDS_HUMAN_REVIEW) for o in outcomes)
        done = sum(bool(o.validated_by) for o in outcomes)
        label = (f"{section} · {present} of {len(outcomes)} present · {done} of {len(outcomes)} validated"
                 + (f" · {open_issues} to look at" if open_issues else ""))
        section_ids = {o.check.id for o in outcomes}
        unread = [(document, record) for document, record in supporting_documents.values()
                  if record["check_id"] in section_ids and document.fingerprint not in in_this_run
                  and document.fingerprint not in section_reads.get(section, set())]
        # Each section stays open or closed as the user left it, even when saving changes the counts in its title
        # (which makes Streamlit draw it afresh). While a status filter is on, matching sections open.
        section_key = f"section_{review_path.stem}_{section}_{line_filter or 'all'}"
        starts_open = bool(line_filter) or open_issues > 0 or bool(unread)
        with st.expander(label, expanded=section_open.get(section_key, starts_open), key=section_key,
                         on_change=remember_section, args=(section_key,)):
            if unread:
                with st.container(horizontal=True, vertical_alignment="center"):
                    st.caption(f":material/attach_file: New in this section: {', '.join(d.name for d, _ in unread)}. "
                               "Re-run it so Clario reads them with the other documents.",
                               width="stretch")
                    if st.button("Re-run this section", icon=":material/refresh:", key=f"rerun_{section}",
                                 disabled=is_demo(), help=DEMO_NOTE if is_demo() else None):
                        try:
                            rerun_section(section, section_ids, unread)
                        except ExtractionFailed as error:
                            st.error(f"Could not re-run the section: {error}", icon=":material/error:")
                        else:
                            st.rerun()
            for o in outcomes_shown:
                render_line(o)

    changed = [line for line in lines if is_changed(line)]
    with st.container(horizontal=True, vertical_alignment="center"):
        if st.button("Save review", type="primary", icon=":material/save:", disabled=not changed,
                     help="Save every changed line at once."):
            problems = save_lines(changed)
            if problems:
                st.error("Nothing was saved yet:\n" + "\n".join(f"- {problem}" for problem in problems),
                         icon=":material/error:")
            else:
                st.rerun()
        st.caption(f"{len(changed)} line(s) with unsaved changes." if changed else "No unsaved changes.")

    def undo_line(check_id: str) -> None:
        remove_override(review_path, check_id)
        log_event(audit_path, reviewer, "Undid the review of this line", check_id)


    if overrides:
        with st.expander(f"Saved reviews of lines ({len(overrides)})"):
            for change in overrides.values():
                with st.container(horizontal=True, vertical_alignment="center"):
                    what = (f"{change.original_status.value} → **{change.status.value}**"
                            if change.status is not change.original_status else "validated")
                    st.markdown(f"**{change.check_id}** · {what} by {change.reviewer} on {change.reviewed_on}"
                                + (f": {change.note}" if change.note else ""), width="stretch")
                    st.button("Undo", key=f"undo_{change.check_id}", icon=":material/undo:",
                              on_click=undo_line, args=(change.check_id,))

    # --- Submit for approval, then final approval by senior management, needed for every review ---

    outstanding = outstanding_lines(replace(result, outcomes=review_outcomes))
    with st.container(border=True):
        st.subheader(":material/send: Submit for approval")
        if submission:
            st.success(f"**Submitted for approval** by {submission['by']} on {submission['on']}. Changing a line "
                       "withdraws the submission.", icon=":material/send:")
        else:
            if outstanding:
                st.warning(f"**Not ready to submit:** every line must be Present and validated. {len(outstanding)} of "
                           f"{len(review_outcomes)} lines are outstanding: " + ", ".join(outstanding) + ".",
                           icon=":material/checklist:")
            else:
                st.success("Every line is Present and validated: the review can be submitted for approval.",
                           icon=":material/task_alt:")
            if st.button("Submit for approval", type="primary", icon=":material/send:",
                         disabled=bool(outstanding) or not reviewer.strip(),
                         help="Recorded under the Reviewer name at the top of the checklist."):
                try:
                    submit_for_approval(review_key, cycle, reviewer, outstanding)
                except ValueError as error:
                    st.error(str(error), icon=":material/error:")
                else:
                    log_event(audit_path, reviewer, f"Submitted the {cycle_name(cycle).lower()} for approval")
                    st.session_state.last_reviewer = reviewer.strip()
                    st.rerun()
            if not reviewer.strip() and not outstanding:
                st.caption("Give your name in **Reviewer** at the top of the checklist to submit.")
            st.caption(":material/info: Final approval opens once the review is submitted.")

    if submission:  # final approval appears once the review has been submitted
        with st.container(border=True):
            st.subheader(":material/verified: Final approval")
            st.caption("Every review needs senior management approval before the client is onboarded. Approving freezes "
                       "the checklist as it stands.")
            with st.form("final_approval"):
                approver = st.text_input("Senior manager")
                approval_note = st.text_area("Note (required to reject)", height=80,
                                             placeholder="e.g. Approved subject to source of wealth evidence")
                with st.container(horizontal=True):
                    approve = st.form_submit_button("Approve review", type="primary", icon=":material/verified:",
                                                    disabled=bool(outstanding) or not submission)
                    reject = st.form_submit_button("Reject review", icon=":material/block:",
                                                   help="Formally reject the assessment; the note is the reason.")
                if approve:
                    try:
                        given = approve_review(approval_path, approver, approval_note, outstanding=outstanding)
                    except ValueError as error:
                        st.error(str(error), icon=":material/error:")
                    else:
                        freeze_now(given)
                        log_event(audit_path, approver, f"Approved the {cycle_name(cycle).lower()}; checklist frozen"
                                  + (f": {approval_note.strip()}" if approval_note.strip() else ""))
                        st.rerun()
                if reject:
                    try:
                        set_status(status_path, REJECTED, approval_note, approver)
                    except ValueError as error:
                        st.error(str(error).replace("Give your name", "Give the senior manager's name"),
                                 icon=":material/error:")
                    else:
                        withdraw_submission(review_key, cycle)
                        log_event(audit_path, approver, f"Rejected the review: {approval_note.strip()}")
                        st.rerun()

    navigation("Ongoing monitoring")
    st.caption(
        "AI findings are decision support: every line is validated by an analyst and every review is approved by "
        "senior management."
    )
