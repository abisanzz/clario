"""Clario review page: add a company's details and documents, and see which checklist items are covered.

Opened from the menu in app/main.py. Run from the project folder:  .venv/bin/streamlit run app/main.py
"""

import sys
from dataclasses import replace
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
    nature_of_business,
    parse_company_number,
)
from services.extractor import ExtractionFailed  # noqa: E402
from services.fca import FcaLookupFailed, FirmNotFound, get_firm, parse_frn  # noqa: E402
from services.audit import describe_line_change, events_csv, load_events, log_event  # noqa: E402
from services.cases import (  # noqa: E402
    DETAIL_FIELDS,
    add_supporting_document,
    answer_paths,
    load_case,
    load_progress,
    load_supporting,
    remove_supporting_document,
    find_by_review_id,
    find_case,
    latest_reviews,
    review_id,
    save_progress,
    save_review,
)
from services.checklist import CHECKLISTS, load_checks  # noqa: E402
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
    fca_source,
    identify_documents,
    pack_fingerprint,
)
from services.reviews import (  # noqa: E402
    save_override,
    approve_review,
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
UPLOAD_TYPES = ["pdf", "png", "jpg", "jpeg", "webp", "gif"]

STATUS_TEXT = {
    Status.PRESENT: "✅ Present",
    Status.MISSING: "❌ Missing",
    Status.UNCLEAR: "⚠️ Unclear",
    Status.NEEDS_HUMAN_REVIEW: "🔎 Needs human review",
    Status.NOT_STARTED: "⏳ Not started",
}
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
st.title("Clario KYC workspace")
st.markdown(
    "Provide the details of the legal entity you are reviewing and upload the documents you hold for it. Clario uses "
    "them to establish the entity's identity, check it against Companies House and the FCA register, understand its "
    "ownership and structure, and map the evidence to the KYC checklist for its industry."
)
st.caption(
    "Make sure the details match the entity's official records. Where information is missing or inconsistent, Clario "
    "lists what to request from the client and what to check on public registers. Every finding shows where it came "
    "from, for you to validate."
)

# --- Screen 1: Legal Entity Information ---
# Streamlit forgets the contents of fields that are not on screen, so "Next" saves them for the session

saved = st.session_state.get("entity", {})


def remembered(field: str, sample_value: str, source: str) -> str:
    """What to show in a field: what was entered before for this choice of documents, else the sample's value."""
    if saved.get("source") == source:
        return saved.get(field, "")
    return sample_value if source == "Sample pack" else ""


WIDGET_PREFIXES = ("entity_name_", "company_link_", "website_", "fca_", "source")


def start_over(entity: dict, case_id: str | None) -> None:
    """Load a draft (or nothing, for a new review): forget the fields' contents and any earlier results."""
    for key in [k for k in st.session_state if str(k).startswith(WIDGET_PREFIXES)]:
        del st.session_state[key]
    for key in ("identification", "labels", "industry", "choice", "assessment", "pack_key"):
        st.session_state.pop(key, None)
    st.session_state.entity, st.session_state.case_id, st.session_state.screen = entity, case_id, "details"


def save_draft(details: dict, documents: list[UploadedDocument]) -> None:
    """Save the review on this computer. One review per legal entity: this replaces any other saved review of it."""
    stored = documents if details["source"] == "Upload documents" else []  # the sample's files stay where they are
    case_id = save_review(st.session_state.get("case_id"), details, stored)
    st.session_state.case_id = case_id
    st.session_state.entity = {**details, "documents": stored, "supporting": saved.get("supporting", [])}


def open_review(case_id: str) -> None:
    """Load a saved review, with its label corrections and industry choice, and show its first screen."""
    details, stored = load_case(case_id)
    start_over({**details, "documents": stored,
                "supporting": [document for document, _ in load_supporting(case_id)]}, case_id)
    progress = load_progress(case_id)
    if progress:
        st.session_state.update(labels=progress["labels"], pack_key=progress["pack_key"])
        if progress["choice"]:
            st.session_state.choice = progress["choice"]
    st.rerun()


def draft_label(draft: dict) -> str:
    saved_at = draft["saved_at"].replace("T", " ")[:16]
    return (f"{draft['review_id']} · {draft['entity_name'] or 'Unnamed entity'} · {draft['documents']} documents · "
            f"saved {saved_at}")


if st.session_state.get("screen", "details") == "details":
    drafts = latest_reviews()  # one per legal entity
    if drafts or st.session_state.get("case_id"):
        with st.container(border=True):
            st.subheader(":material/folder_open: Your saved reviews")
            if st.session_state.get("case_id"):
                st.caption(f"You are working on saved review **{review_id(st.session_state.case_id)}**: "
                           f"{saved.get('entity_name') or 'Unnamed entity'}. Changes are saved when you click Next or "
                           "Save as draft.")
            with st.container(horizontal=True, vertical_alignment="bottom"):
                typed_id = st.text_input("Find a review by ID", placeholder="e.g. CLR-E9BD2CD5", width="stretch",
                                         help="Each legal entity's review has its own ID, shown at the top of the "
                                              "review. Type it to open the latest review of that entity.")
                if st.button("Find", icon=":material/search:", disabled=not typed_id.strip()):
                    found = find_by_review_id(typed_id)
                    if found:
                        open_review(found)
                    st.error(f"No saved review has the ID {typed_id.strip().upper()}.", icon=":material/error:")
            with st.container(horizontal=True, vertical_alignment="bottom"):
                by_id = {d["id"]: d for d in drafts}
                chosen = st.selectbox("Continue a saved review", list(by_id), format_func=lambda i: draft_label(by_id[i]),
                                      index=None, placeholder="Choose a review", width="stretch") if drafts else None
                if st.button("Open review", icon=":material/folder_open:", disabled=not chosen):
                    open_review(chosen)
                if st.button("Start a new review", icon=":material/add:"):
                    start_over({}, None)
                    st.rerun()

    with st.container(border=True):
        st.subheader(":material/upload_file: Legal Entity Information")
        # The documents choice sits below the fields but decides what they are filled with, so read its last setting
        source = st.session_state.get("source") or saved.get("source") or "Sample pack"

        entity_name = st.text_input(
            "Legal Entity Full Name",
            value=remembered("entity_name", SAMPLE_ENTITY_NAME, source),
            key=f"entity_name_{source}",
            help="Enter the full registered legal name of the entity you are conducting business with.",
        )
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
        website = st.text_input("Company website", value=remembered("website", "", source), key=f"website_{source}",
                                placeholder="e.g. example.com")
        fca_frn = st.text_input(
            "FCA firm reference number", key=f"fca_{source}", placeholder="e.g. 730427",
            value=remembered("fca_frn", SAMPLE_FCA_FRN, source),
            help="The 6 or 7 digit FRN on the firm's FCA register page. Leave empty if the firm is not FCA regulated.",
        )
        show_fca_firm(fca_frn, company_link)
        existing = find_case({"entity_name": entity_name, "company_link": company_link})
        if existing and existing["id"] != st.session_state.get("case_id"):
            with st.container(border=True):
                st.warning(
                    f"A saved review already exists for {existing['entity_name'] or 'this entity'} "
                    f"({draft_label(existing)}). Each legal entity has one review, so saving this one will replace "
                    "it. To add to the saved review instead, open it.", icon=":material/warning:")
                if st.button("Open the saved review", icon=":material/folder_open:"):
                    open_review(existing["id"])

        source = st.segmented_control(
            "Documents", ["Sample pack", "Upload documents"], default=saved.get("source", "Sample pack"), key="source"
        ) or "Sample pack"
        if source == "Sample pack":
            documents = SAMPLE_DOCUMENTS
            st.caption(
                f"{len(documents)} specimen documents for the fictitious EXAMPLE PAYMENTS LTD, with deliberate gaps. "
                "Saved answers are replayed, so the sample costs nothing to run."
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
            uploads = st.file_uploader("Add documents (PDFs or photos)" if earlier else "Company documents (PDFs or photos)",
                                       type=UPLOAD_TYPES, accept_multiple_files=True)
            added = [UploadedDocument(u.name, u.getvalue(), u.type or "application/pdf") for u in uploads or []]
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
                        help="Claude reads this as a hint when identifying the document and running the checks.")
                    described.append(replace(document, description=text.strip()))
                documents = described
            st.caption(
                ":material/lock: Only upload fictitious or approved documents: files are sent to Anthropic to be read.")

    details = {"source": source, "entity_name": entity_name, "company_link": company_link, "website": website,
               "fca_frn": fca_frn}
    with st.container(horizontal=True):
        if st.button("Save as draft", icon=":material/save:"):
            save_draft(details, documents)
            st.toast(f"Saved on this computer. Its review ID is {review_id(st.session_state.case_id)}: use it to find "
                     "this review any time.", icon=":material/check_circle:")
        if st.button("Next", type="primary", icon=":material/arrow_forward:", disabled=not documents):
            save_draft(details, documents)  # every review is saved, so it can be reopened and amended later
            st.session_state.screen = "documents"
            st.rerun()
    if not documents:
        st.caption("Add at least one document to continue.")
    elif source == "Upload documents":
        st.caption(f"Next asks Claude to identify each document (roughly 1p per document, about "
                   f"${len(documents) * 0.011:.2f} for these {len(documents)}). A reopened draft with the same "
                   "documents costs nothing.")
    st.stop()

# --- Screens 2 to 5: the checks, using the saved details ---

SCREENS = ["details", "documents", "assess", "results"]
screen = st.session_state.screen if st.session_state.get("screen") in SCREENS else "documents"

source = saved["source"]
entity_name, company_link, website, fca_frn = (saved[k] for k in ("entity_name", "company_link", "website", "fca_frn"))
documents = (SAMPLE_DOCUMENTS if source == "Sample pack" else saved["documents"]) + saved.get("supporting", [])
saved_answers = SAMPLE_ANSWERS if source == "Sample pack" else answer_paths(st.session_state.case_id)


def go(to: str) -> None:
    st.session_state.screen = to
    st.rerun()


def navigation(next_label: str | None = None, next_ready: bool = True, save=None) -> None:
    """Back and Next buttons. save runs first on either, so this screen's choices are kept whichever way you go."""
    position = SCREENS.index(screen)
    with st.container(horizontal=True):
        if st.button("Back", icon=":material/arrow_back:", key=f"back_{screen}"):
            if save and next_ready:
                save()
            go(SCREENS[position - 1])
        if next_label and st.button(next_label, type="primary", icon=":material/arrow_forward:",
                                    disabled=not next_ready, key=f"next_{screen}"):
            if save:
                save()
            go(SCREENS[position + 1])


with st.container(border=True):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.subheader(":material/domain: " + (entity_name or "Legal entity"), width="stretch")
        if st.button("Edit details", icon=":material/edit:"):
            go("details")
    summary = [("Company", company_link), ("FCA FRN", fca_frn), ("Website", website),
               ("Documents", f"{len(documents)} files")]
    st.caption(" · ".join(f"{label}: {value}" for label, value in summary if value))
    if st.session_state.get("case_id"):
        st.caption(f":material/badge: Review ID **{review_id(st.session_state.case_id)}** · "
                   ":material/cloud_done: Saved on this computer. You can close Clario and reopen this review from "
                   "Your saved reviews on the Review page.")
st.caption(f"Step {SCREENS.index(screen) + 1} of {len(SCREENS)}")

# Start again whenever the set of documents changes
pack_key = pack_fingerprint(documents)
# Line reviews, the risk decision and the final approval belong to the review, so adding documents keeps them
review_key = st.session_state.get("case_id") or pack_key
audit_path = case_file(review_key, "audit").with_suffix(".jsonl")  # who changed what, and when

stored_supporting = load_supporting(st.session_state.case_id) if st.session_state.get("case_id") else []
original_documents = SAMPLE_DOCUMENTS if source == "Sample pack" else saved["documents"]


def quotes_from(name: str, evidence: list[str]) -> bool:
    """Does any quoted evidence come from this document? Quotes start with the document's name."""
    return any(quote.startswith((f"{name}:", f"{name} p.")) for quote in evidence)


def lines_review_path() -> Path | None:
    chosen_checklist = st.session_state.get("choice", (None, None))[1]
    return case_file(review_key, chosen_checklist) if chosen_checklist else None


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


def delete_document(document: UploadedDocument, record: dict | None) -> None:
    """Delete a document from the review. Deleting an original document means it is identified and checked again."""
    if record:  # a supporting document added on the results screen
        remove_supporting_document(st.session_state.case_id, document.fingerprint)
        path = lines_review_path()
        for override in list(load_overrides(path).values()) if path else []:
            if override.via == document.name:  # the line it set to Present goes back to its previous status
                remove_override(path, override.check_id)
                log_event(audit_path, st.session_state.get("last_reviewer", ""),
                          f"Line went back to {override.original_status.value} because {document.name} was deleted",
                          override.check_id)
        st.session_state.entity = {**saved, "supporting": [d for d in saved.get("supporting", [])
                                                            if d.fingerprint != document.fingerprint]}
    else:
        remaining = [d for d in saved["documents"] if d.fingerprint != document.fingerprint]
        save_review(st.session_state.case_id, {k: saved[k] for k in DETAIL_FIELDS}, remaining)
        st.session_state.entity = {**saved, "documents": remaining}
        if not remaining:
            st.session_state.screen = "details"
    log_event(audit_path, st.session_state.get("last_reviewer", ""), f"Deleted document {document.name}",
              f"check {record['check_id']}" if record else "")
    st.session_state.pop("delete_pending", None)


with st.expander(f"Documents ({len(original_documents) + len(stored_supporting)})", icon=":material/folder_open:"):
    rows = [(d, None) for d in original_documents] + list(stored_supporting)
    for document, record in rows:
        name_side, description_side, delete_side = st.columns([3, 4, 1], vertical_alignment="center")
        name_side.markdown(f"**{document.name}**"
                           + (f"  \n:gray[Supporting document for check {record['check_id']}]" if record else ""))
        description = record.get("description", "") if record else document.description
        description_side.caption(description or "No description given")
        sample_file = source == "Sample pack" and not record
        if delete_side.button("Delete", icon=":material/delete:", key=f"delete_{document.fingerprint}",
                              disabled=sample_file, help="The sample's documents cannot be deleted." if sample_file
                              else "Remove this document from the review."):
            st.session_state.delete_pending = document.fingerprint
        if st.session_state.get("delete_pending") == document.fingerprint:
            with st.container(border=True):
                used_for = dependants(document)
                st.warning(f"Delete **{document.name}**?"
                           + ("  \nThis document was used for:" + "".join(f"\n- {item}" for item in used_for)
                              + "\n\nDeleting it will change these: they will be worked out again without this "
                              "document." if used_for else "")
                           + ("" if record else "  \nThe remaining documents will be identified and checked again "
                              "(roughly 3-4p per document for your own uploads). Your line reviews, risk rating and "
                              "approval are kept."),
                           icon=":material/delete:")
                with st.container(horizontal=True):
                    if st.button("Yes, delete", type="primary", key=f"confirm_{document.fingerprint}"):
                        delete_document(document, record)
                        st.rerun()
                    if st.button("Cancel", key=f"cancel_{document.fingerprint}"):
                        st.session_state.pop("delete_pending", None)
                        st.rerun()
if st.session_state.get("pack_key") != pack_key:
    st.session_state.pack_key = pack_key
    for key in ("identification", "labels", "industry", "choice", "assessment"):
        st.session_state.pop(key, None)

def remember(**choices) -> None:
    """Keep the reviewer's label corrections or industry choice for this session, and in the draft if there is one."""
    st.session_state.update(choices)
    if st.session_state.get("case_id"):
        save_progress(st.session_state.case_id, pack_key, st.session_state.get("labels"),
                      st.session_state.get("choice"))


# --- Screen 2: what each document is ---

if screen == "documents":
    with st.container(border=True):
        st.subheader(":material/plagiarism: Check what each document is")
        if "identification" not in st.session_state:  # identify straight away when this screen opens
            with st.spinner(f"Claude is reading the {len(documents)} documents..."):
                try:
                    st.session_state.identification = identify_documents(
                        documents, saved_answer=saved_answers.get("labels"))
                except (ExtractionFailed, UnsupportedFile) as error:
                    st.error(f"Could not identify the documents: {error}", icon=":material/error:")
                    st.button("Try again", icon=":material/refresh:")
        if "identification" in st.session_state:
            identification = st.session_state.identification
            shown = st.session_state.get("labels") or identification.labels  # your corrections, if you made any
            description_of = {d.name: d.description for d in documents}
            st.caption("Change a label if Claude got it wrong. The checks use these labels. Open **Details** to see "
                       "Claude's reason.")
            confirmed = []
            for number, label in enumerate(shown):
                with st.container(border=True):
                    name_side, type_side = st.columns([3, 2], vertical_alignment="center")
                    name_side.markdown(f"**{label.name}**")
                    if description_of.get(label.name):
                        name_side.caption(f"Your description: {description_of[label.name]}")
                    chosen_type = type_side.selectbox(
                        f"Document type of {label.name}", list(DOCUMENT_TYPES.values()),
                        index=list(DOCUMENT_TYPES).index(label.document_type), key=f"type_{pack_key}_{number}",
                        label_visibility="collapsed", help="Change this if Claude got it wrong.")
                    with st.expander("Details"):
                        st.markdown(label.reason or "No reason given.")
                    confirmed.append(DocumentLabel(label.name, TYPE_KEY[chosen_type], label.reason))
            st.caption("Labels: replayed, $0.00" if identification.replayed
                       else f"Labels: about ${identification.cost_usd:.3f}")
    navigation("Next", "identification" in st.session_state, save=lambda: remember(labels=confirmed))
    if source == "Upload documents":
        st.caption("Next asks Claude to suggest the industry and an initial risk rating (roughly 13-18p together). A "
                   "reopened review with unchanged documents costs nothing.")
    st.stop()

confirmed = st.session_state.get("labels") or []
identification = st.session_state.get("identification")
if not confirmed or identification is None:
    go("documents")

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

decision_path = case_file(review_key, "risk-decision")
links_key = (tuple(confirmed), company_link.strip(), website.strip(), fca_frn.strip())
if st.session_state.get("industry") and st.session_state.industry[0] != links_key:
    st.session_state.pop("industry")  # documents, labels or links changed
    st.session_state.pop("choice", None)

if screen == "assess":
    sources, link_warnings = fetch_links(company_link, website, fca_frn)
    for warning in link_warnings:
        st.warning(warning, icon=":material/warning:")
    if "industry" not in st.session_state:  # both suggestions start straight away when this screen opens
        with st.spinner("Claude is reading the questionnaire, the registers and the website to work out the "
                        "industry..."):
            try:
                st.session_state.industry = (links_key, suggest_industry(
                    documents, confirmed, sources, saved_answer=saved_answers.get("industry")))
            except (ExtractionFailed, UnsupportedFile) as error:
                st.error(f"Could not suggest the industry: {error}", icon=":material/error:")
                st.button("Try again", icon=":material/refresh:")
                navigation()
                st.stop()
    suggestion = st.session_state.industry[1]
    risk_key = (pack_key, tuple(confirmed), suggestion.industry, tuple(sources))
    if st.session_state.get("risk", (None,))[0] != risk_key:
        with st.spinner("Claude is rating the risk from the ownership and business documents, the registers and the "
                        "website..."):
            try:
                st.session_state.risk = (risk_key, suggest_risk(
                    documents, confirmed, INDUSTRIES[suggestion.industry], sources,
                    saved_answer=saved_answers.get("risk"),
                    update_saved=source != "Sample pack"))  # the sample's free demo answer is never replaced
            except (ExtractionFailed, UnsupportedFile) as error:
                st.error(f"Could not suggest a risk rating: {error}", icon=":material/error:")
                st.button("Try again", icon=":material/refresh:")
                navigation()
                st.stop()
    risk = st.session_state.risk[1]
    decision = load_risk_decision(decision_path)
    chosen_industry = st.session_state.get("choice", (suggestion.industry, None))[0]
    if chosen_industry not in INDUSTRIES:  # e.g. "Not enough information" in a review saved before it was removed
        chosen_industry = suggestion.industry

    st.subheader(":material/fact_check: Industry, risk rating and checklist")
    st.caption("Clario's suggestions are below. Change any of them if you disagree, and open **Why** to see Claude's "
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
            industry = INDUSTRY_KEY[st.selectbox(
                "Override Industry", list(INDUSTRIES.values()), index=list(INDUSTRIES).index(chosen_industry),
                key=f"industry_{hash(links_key)}", help="Change this if Claude got it wrong.",
            )]
            with st.expander("Why this industry?"):
                st.markdown(suggestion.reason)
                if suggestion.sources_agree == "no":
                    st.warning(f"**The sources disagree.** {suggestion.disagreement}", icon=":material/warning:")
                else:
                    st.caption(SOURCES_AGREE[suggestion.sources_agree])
                if suggestion.evidence:
                    st.markdown("**Evidence**\n" + "\n".join(f"- {quote}" for quote in suggestion.evidence))
                st.caption("Replayed, $0.00" if suggestion.replayed else f"About ${suggestion.cost_usd:.3f}")
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
            st.caption("Replayed, $0.00" if risk.replayed else f"About ${risk.cost_usd:.3f}")

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
                upload = st.file_uploader("Sign-off document", key=f"evidence_{pack_key}",
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
    if source == "Upload documents":
        st.caption(f"Next saves your choices and runs the KYC checks: Claude reads every document again against the "
                   f"checklist (roughly 3p per document, about ${len(documents) * 0.027:.2f} for these "
                   f"{len(documents)}). A reopened review with unchanged documents and checklist costs nothing.")
    elif checklist != SAMPLE_CHECKLIST:
        st.caption(f":material/payments: The sample's saved answer is for the {CHECKLISTS[SAMPLE_CHECKLIST][0]} "
                   "checklist. With this checklist, Next asks Claude to run the checks again (about 20p).")
    st.stop()

decision = load_risk_decision(decision_path)
if "industry" not in st.session_state or not st.session_state.get("choice", (None, None))[1] or decision is None:
    go("assess")
suggestion = st.session_state.industry[1]
industry, checklist = st.session_state.choice

# Results no longer match if the labels or the checklist changed
if st.session_state.get("assessment") and st.session_state.assessment[0] != (confirmed, checklist):
    st.session_state.pop("assessment")

# --- Screen 5: results. The checks run as this screen opens, then the results appear ---

if "assessment" not in st.session_state:
    replay_sample = source == "Sample pack" and checklist == SAMPLE_CHECKLIST
    sources, _ = fetch_links(company_link, website, fca_frn)
    with st.spinner(f"Claude is checking the {len(documents)} documents against every item on the "
                    f"{CHECKLISTS[checklist][0]} checklist. This can take a minute..."):
        try:
            st.session_state.assessment = ((confirmed, checklist), assess_pack(
                documents, confirmed, sources, checklist=CHECKLISTS[checklist][1],
                saved_answer=saved_answers.get("assessment") if replay_sample or source != "Sample pack" else None,
            ))
        except ExtractionFailed as error:
            st.error(f"Could not run the checks: {error}", icon=":material/error:")
            st.button("Try again", icon=":material/refresh:")
            navigation()
            st.stop()
original = st.session_state.assessment[1]

# The analyst's saved changes for this set of documents and checklist
review_path = case_file(review_key, checklist)
overrides = load_overrides(review_path)
# The legal entity name rule on check 1.1, then the analyst's changes, which always have the final say
named = apply_entity_name(original, entity_name, parse_company_number(company_link), lookup=cached_company)
result = apply_overrides(named, overrides)

approval_path = case_file(review_key, "final-approval")
approval = load_approval(approval_path)

st.header("Results")
with st.container(border=True, horizontal=True, vertical_alignment="center"):
    with st.container():
        st.caption("Risk rating")
        st.markdown(f"#### :{RATING_COLOURS[decision.rating]}[{decision.rating}]")
        if decision.overridden:
            st.caption(f"Overriding Clario's {decision.suggested}; signed off by {decision.reviewer}, AML senior "
                       "officer")
    with st.container():
        st.caption("Checklist")
        st.markdown(f"#### {CHECKLISTS[checklist][0]}")
        st.caption(f"{len(result.outcomes)} checks · Industry: {INDUSTRIES[industry]}")
    with st.container():
        st.caption("Final approval")
        if approval:
            st.markdown(f"#### :green[Approved]")
            st.caption(f"By {approval.approver} on {approval.approved_on}")
        else:
            st.markdown("#### :orange[Awaiting]")
            st.caption("Senior management approves at the end of this page")
total = identification.cost_usd + suggestion.cost_usd + original.cost_usd
st.caption("Checks: replayed, $0.00" if original.replayed
           else f"Checks: about ${original.cost_usd:.3f}. Total for this company: about ${total:.3f}")
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

# --- Every check, validated line by line ---

st.subheader("Every check, by section")
st.caption(
    "For each line: tick **Validated** once you have checked it, change the **Status** if you disagree (a "
    "**comment** is then required), and open **Details** for the finding, Claude's view, who decided and the "
    "evidence, or to upload supporting documents. Then click **Save review**. :material/lock: Saved on this computer "
    "only."
)
validated_count = sum(bool(o.validated_by) for o in result.outcomes)
st.progress(validated_count / len(result.outcomes),
            text=f"{validated_count} of {len(result.outcomes)} lines validated")

supporting_by_check, supporting_documents = {}, {}
if st.session_state.get("case_id"):
    for document, record in load_supporting(st.session_state.case_id):
        supporting_by_check.setdefault(record["check_id"], []).append(record)
        supporting_documents[document.fingerprint] = (document, record)
in_this_run = {d.fingerprint for d in documents}
section_reads = st.session_state.setdefault("section_reads", {})  # section -> documents its re-run has read
not_yet_read = [r for _, r in supporting_documents.values() if r["sha256"] not in in_this_run]
if not_yet_read:
    with st.container(border=True):
        st.info(f"{len(not_yet_read)} supporting document(s) added since the checks ran: "
                + ", ".join(r["name"] for r in not_yet_read) + ". Re-run the section they belong to (button in each "
                "section), or re-run all the checks, so Claude reads them with the rest of the documents.",
                icon=":material/attach_file:")
        if st.button("Re-run all the checks with the new documents", icon=":material/refresh:"):
            st.session_state.entity = {**saved, "supporting": [d for d, _ in supporting_documents.values()]}
            go("documents")
        st.caption(f"Re-running everything reads every document again, with the industry and risk rating (about "
                   f"${(len(documents) + len(not_yet_read)) * 0.027 + 0.15:.2f}). Your line reviews are kept.")


def rerun_section(section: str, check_ids: set[str], unread: list[tuple[UploadedDocument, dict]]) -> None:
    """Re-check one section with every document, including supporting ones Claude has not read yet."""
    extra_docs = [document for document, _ in unread]
    extra_labels = [DocumentLabel(document.name, "other", f"Supporting document added for check {record['check_id']}")
                    for document, record in unread]
    sources, _ = fetch_links(company_link, website, fca_frn)
    with st.spinner(f"Claude is re-checking {section} with {len(documents) + len(extra_docs)} documents..."):
        partial = assess_pack(documents + extra_docs, confirmed + extra_labels, sources,
                              checklist=CHECKLISTS[checklist][1], only=check_ids)
    new_lines = {o.check.id: o for o in partial.outcomes}
    key, current = st.session_state.assessment
    st.session_state.assessment = (key, replace(
        current, outcomes=[new_lines.get(o.check.id, o) for o in current.outcomes], replayed=False,
        input_tokens=current.input_tokens + partial.input_tokens,
        output_tokens=current.output_tokens + partial.output_tokens))
    section_reads[section] = section_reads.get(section, set()) | {d.fingerprint for d in extra_docs}
    log_event(audit_path, st.session_state.get("last_reviewer", ""),
              "Re-ran the section with " + ", ".join(d.name for d in extra_docs), section)


reviewer = st.text_input("Reviewer", value=st.session_state.get("last_reviewer", ""), width=300,
                         help="Your name, recorded against every line you validate or change.")
line_versions = st.session_state.setdefault("line_versions", {})  # a line's fields start fresh after it is saved


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
        document = UploadedDocument(upload.name, upload.getvalue(), upload.type or "application/pdf")
        verdict = None
        if o.status is not Status.PRESENT:  # Claude reads it against this one line
            with st.spinner(f"Claude is reading {document.name} against check {o.check.id}..."):
                try:
                    verdict = read_supporting_document(o.check, o.finding, document, description)
                except (ExtractionFailed, UnsupportedFile) as error:
                    st.warning(f"{document.name} was added, but Claude could not read it ({error}).",
                               icon=":material/warning:")
        add_supporting_document(st.session_state.case_id, document, o.check.id, reviewer,
                                verdict=verdict.label if verdict else "",
                                verdict_finding=verdict.finding if verdict else "", description=description)
        log_event(audit_path, reviewer, f"Added supporting document {document.name}"
                  + (f' ("{description.strip()}")' if description.strip() else ""), o.check.id)
        if verdict and verdict.satisfies == "yes" and o.check.id not in changed_by_you:
            explanation = verdict.finding + "".join(f" {quote}" for quote in verdict.evidence[:1])
            note = (f"{comment.strip()} (Claude, from {document.name}: {explanation})" if comment.strip()
                    else f"Claude, from {document.name}: {explanation}")
            save_override(review_path, named, o.check.id, Status.PRESENT, note, reviewer or "Clario",
                          validated=validated, via=document.name)
        if verdict:
            log_event(audit_path, "Claude", f"Read {document.name}: {verdict.label}"
                      + (f" → status {o.status.value} → Present" if verdict.satisfies == "yes"
                         and o.check.id not in changed_by_you else ""), o.check.id)
    if reviewer.strip():
        st.session_state.last_reviewer = reviewer.strip()
    for o, *_ in selected:
        line_versions[o.check.id] = line_versions.get(o.check.id, 0) + 1
    return []


lines = []  # (outcome, status, validated, comment, uploads, description) as shown on screen
for section, outcomes in groupby(result.outcomes, key=lambda o: o.check.section):
    outcomes = list(outcomes)
    present = sum(o.status is Status.PRESENT for o in outcomes)
    open_issues = sum(o.status in (Status.MISSING, Status.UNCLEAR, Status.NEEDS_HUMAN_REVIEW) for o in outcomes)
    done = sum(bool(o.validated_by) for o in outcomes)
    label = (f"{section} · {present} of {len(outcomes)} present · {done} of {len(outcomes)} validated"
             + (f" · {open_issues} to look at" if open_issues else ""))
    section_ids = {o.check.id for o in outcomes}
    unread = [(document, record) for document, record in supporting_documents.values()
              if record["check_id"] in section_ids and document.fingerprint not in in_this_run
              and document.fingerprint not in section_reads.get(section, set())]
    with st.expander(label, expanded=open_issues > 0 or bool(unread)):
        if unread:
            with st.container(horizontal=True, vertical_alignment="center"):
                st.caption(f":material/attach_file: New in this section: {', '.join(d.name for d, _ in unread)}. "
                           f"Re-run it so Claude reads them with the other documents (roughly 10-15p).",
                           width="stretch")
                if st.button("Re-run this section", icon=":material/refresh:", key=f"rerun_{section}"):
                    try:
                        rerun_section(section, section_ids, unread)
                    except ExtractionFailed as error:
                        st.error(f"Could not re-run the section: {error}", icon=":material/error:")
                    else:
                        st.rerun()
        for o in outcomes:
            key = f"{review_path.stem}_{o.check.id}_{line_versions.get(o.check.id, 0)}"
            with st.container(border=True):
                text_side, status_side, tick_side = st.columns([5, 2, 1], vertical_alignment="center")
                text_side.markdown(f"**{o.check.id}** {o.check.check}")
                status = STATUS_FROM_TEXT[status_side.selectbox(
                    "Status", list(STATUS_TEXT.values()), index=list(STATUS_TEXT).index(o.status),
                    key=f"status_{key}", label_visibility="collapsed")]
                validated = tick_side.checkbox("Validated", value=bool(o.validated_by), key=f"validated_{key}")
                comment_side, line_save_side = st.columns([6, 1], vertical_alignment="center")
                comment = comment_side.text_input(
                    "Comment", value=o.reviewer_note, key=f"comment_{key}", label_visibility="collapsed",
                    placeholder="Comment (required if you change the status)")
                with st.expander("Details"):
                    st.markdown(f"**Finding:** {o.finding}")
                    if o.claude_finding:
                        st.markdown(f"**Claude's view:** {o.claude_finding}")
                    st.markdown(f"**Decided by:** {o.decided_by}"
                                + (f" · **Validated by:** {o.validated_by}" if o.validated_by else ""))
                    if o.before_review:
                        st.markdown(f"**Before the change:** {o.before_review}")
                    st.markdown("**Evidence:**" + ("".join(f"\n- {quote}" for quote in o.evidence)
                                                    if o.evidence else " none quoted"))
                    for record in supporting_by_check.get(o.check.id, []):
                        st.caption(f":material/attach_file: Supporting document: {record['name']}"
                                   + (f" ({record['description']})" if record.get("description") else "")
                                   + ", added" + (f" by {record['added_by']}" if record["added_by"] else "")
                                   + f" on {record['added_on']}"
                                   + (f". Claude: {record['verdict']}. {record.get('verdict_finding', '')}"
                                      if record.get("verdict") else ""))
                # Add a supporting document: upload, describe it and save, in a fold-out section
                with st.expander("Upload supporting document", icon=":material/attach_file:"):
                    uploads = st.file_uploader(
                        "Document", type=UPLOAD_TYPES, accept_multiple_files=True, key=f"upload_{key}",
                        help="Added to the review's document store when you save this line.")
                    description = st.text_input(
                        "What does this document show? (optional)", key=f"description_{key}",
                        placeholder="e.g. Updated register of members, dated 20 Oct 2026",
                        help="Claude reads this with the document to understand what it is for.")
                    if uploads and o.status is not Status.PRESENT:
                        st.caption(":material/smart_toy: When you save, Claude reads the document against this "
                                   "check (roughly 1-3p) and sets the line to Present if it provides the evidence.")
                    upload_save = st.button("Save", icon=":material/save:", key=f"save_upload_{key}",
                                            disabled=not uploads, help="Add the document and save this line.")
                line = (o, status, validated, comment or "", uploads or [], description or "")
                lines.append(line)
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

# --- Final approval by senior management, needed for every review ---

def withdraw(who: str) -> None:
    withdraw_approval(approval_path)
    log_event(audit_path, who, f"Withdrew the approval given by {approval.approver} on {approval.approved_on}")


with st.container(border=True):
    st.subheader(":material/verified: Final approval")
    if approval:
        st.success(f"**Approved by {approval.approver}** on {approval.approved_on}"
                   + (f": {approval.note}" if approval.note else "."), icon=":material/verified:")
        st.button("Withdraw approval", icon=":material/undo:", on_click=withdraw, args=(reviewer,),
                  help="Recorded in the audit log under the Reviewer name at the top of the checklist.")
    else:
        st.caption("Every review needs senior management approval before the client is onboarded.")
        remaining = len(result.outcomes) - validated_count
        if remaining:
            st.warning(f"{remaining} of {len(result.outcomes)} lines have not been validated yet.",
                       icon=":material/checklist:")
        with st.form("final_approval"):
            approver = st.text_input("Senior manager")
            approval_note = st.text_area("Note (optional)", height=80,
                                         placeholder="e.g. Approved subject to source of wealth evidence")
            if st.form_submit_button("Approve review", type="primary", icon=":material/verified:"):
                try:
                    approve_review(approval_path, approver, approval_note)
                except ValueError as error:
                    st.error(str(error), icon=":material/error:")
                else:
                    log_event(audit_path, approver, "Approved the review"
                              + (f": {approval_note.strip()}" if approval_note.strip() else ""))
                    st.rerun()

# --- Audit log ---

events = load_events(audit_path)
with st.expander(f"Audit log ({len(events)} entries)", icon=":material/history:"):
    if events:
        st.dataframe(pd.DataFrame([{"Time": e.at, "Who": e.who, "Line": e.line, "What": e.what} for e in events]),
                     hide_index=True, column_config={"What": st.column_config.TextColumn(width="large")})
        st.download_button("Download the audit log (CSV)", events_csv(events), file_name="clario-audit-log.csv",
                           mime="text/csv", icon=":material/download:")
    else:
        st.caption("Nothing recorded yet.")
    st.caption("Every change is recorded here with who made it and when. Entries are only ever added.")

navigation()
st.caption(
    "Items marked 🔎 must be reviewed by an analyst. Clario supports, and does not replace, a KYC review. "
    "Not legal advice."
)
