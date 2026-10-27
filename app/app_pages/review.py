"""Clario review page: add a company's details and documents, and see which checklist items are covered.

Opened from the menu in app/main.py. Run from the project folder:  .venv/bin/streamlit run app/main.py
"""

import sys
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
from services.cases import (  # noqa: E402
    answer_paths,
    load_case,
    load_progress,
    find_by_review_id,
    find_case,
    latest_reviews,
    review_id,
    save_progress,
    save_review,
)
from services.checklist import CHECKLISTS  # noqa: E402
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
from services.reviews import apply_overrides, case_file, load_overrides, remove_override, save_override  # noqa: E402
from services.validator import Status, entity_name_matches  # noqa: E402
from services.website import WebsiteFetchFailed, website_text  # noqa: E402

SAMPLES = PROJECT_ROOT / "sample_documents"
SAMPLE_FILES = [SAMPLES / "certificate_of_incorporation.pdf"] + sorted((SAMPLES / "pack").glob("*.pdf"))
SAMPLE_DOCUMENTS = [UploadedDocument(f.name, f.read_bytes()) for f in SAMPLE_FILES]
SAMPLE_ANSWERS = {
    "labels": SAMPLES / "pack_labels.answer.json",
    "industry": SAMPLES / "pack_industry.answer.json",
    "assessment": SAMPLES / "pack_assessment.answer.json",
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
INDUSTRY_KEY = {label: key for key, label in INDUSTRIES.items()}
CHECKLIST_KEY = {name: key for key, (name, _) in CHECKLISTS.items()}
SAMPLE_CHECKLIST = "fintech"  # the checklist the sample pack's saved answer was made with


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
    st.session_state.entity = {**details, "documents": stored}


def open_review(case_id: str) -> None:
    """Load a saved review, with its label corrections and industry choice, and show its first screen."""
    details, stored = load_case(case_id)
    start_over({**details, "documents": stored}, case_id)
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

SCREENS = ["details", "documents", "industry", "results"]
screen = st.session_state.screen if st.session_state.get("screen") in SCREENS else "documents"

source = saved["source"]
entity_name, company_link, website, fca_frn = (saved[k] for k in ("entity_name", "company_link", "website", "fca_frn"))
documents = SAMPLE_DOCUMENTS if source == "Sample pack" else saved["documents"]
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
            st.caption("Change a label if Claude got it wrong. The checks use these labels.")
            edited = st.data_editor(
                pd.DataFrame([{"File": label.name, "Document type": label.type_label, "Why": label.reason}
                              for label in shown]),
                column_config={
                    "Document type": st.column_config.SelectboxColumn(options=list(DOCUMENT_TYPES.values()),
                                                                      required=True),
                    "Why": st.column_config.TextColumn("Why Claude thinks so"),
                },
                disabled=["File", "Why"],
                hide_index=True,
                key=f"labels_{pack_key}",
            )
            confirmed = [DocumentLabel(row["File"], TYPE_KEY[row["Document type"]], row["Why"])
                         for _, row in edited.iterrows()]
            st.caption("Labels: replayed, $0.00" if identification.replayed
                       else f"Labels: about ${identification.cost_usd:.3f}")
    navigation("Next", "identification" in st.session_state, save=lambda: remember(labels=confirmed))
    if source == "Upload documents":
        st.caption("Next asks Claude to suggest the industry (roughly 3p). A reopened draft with unchanged documents "
                   "costs nothing.")
    st.stop()

confirmed = st.session_state.get("labels") or []
identification = st.session_state.get("identification")
if not confirmed or identification is None:
    go("documents")

# --- Screen 3: industry and checklist ---

links_key = (tuple(confirmed), company_link.strip(), website.strip(), fca_frn.strip())
if st.session_state.get("industry") and st.session_state.industry[0] != links_key:
    st.session_state.pop("industry")  # documents, labels or links changed
    st.session_state.pop("choice", None)

if screen == "industry":
    with st.container(border=True):
        st.subheader(":material/domain: Confirm the industry and checklist")
        if "industry" not in st.session_state:  # suggest straight away when this screen opens
            sources, link_warnings = fetch_links(company_link, website, fca_frn)
            for warning in link_warnings:
                st.warning(warning, icon=":material/warning:")
            with st.spinner("Claude is reading the questionnaire, the registers and the website to work out the "
                            "industry..."):
                try:
                    suggestion = suggest_industry(documents, confirmed, sources, saved_answer=saved_answers.get("industry"))
                    st.session_state.industry = (links_key, suggestion)
                except (ExtractionFailed, UnsupportedFile) as error:
                    st.error(f"Could not suggest the industry: {error}", icon=":material/error:")
                    st.button("Try again", icon=":material/refresh:")
        if "industry" in st.session_state:
            suggestion = st.session_state.industry[1]
            st.markdown(f"**Claude suggests:** {suggestion.industry_label}  \n{suggestion.reason}")
            if suggestion.sources_agree == "no":
                st.warning(f"**The sources disagree.** {suggestion.disagreement}", icon=":material/warning:")
            else:
                st.caption(SOURCES_AGREE[suggestion.sources_agree])
            if suggestion.evidence:
                with st.expander("Evidence"):
                    st.markdown("\n".join(f"- {quote}" for quote in suggestion.evidence))
            chosen_industry, chosen_checklist = st.session_state.get("choice", (suggestion.industry, None))
            industry = INDUSTRY_KEY[st.selectbox(
                "Industry", list(INDUSTRIES.values()), index=list(INDUSTRIES).index(chosen_industry),
                key=f"industry_{hash(links_key)}", help="Change this if Claude got it wrong.",
            )]
            suggested_checklist, written_for_industry = checklist_for(industry)
            if industry != chosen_industry or chosen_checklist is None:
                chosen_checklist = suggested_checklist
            checklist = CHECKLIST_KEY[st.selectbox(
                "Checklist", [name for name, _ in CHECKLISTS.values()], index=list(CHECKLISTS).index(chosen_checklist),
                key=f"checklist_{hash(links_key)}_{industry}",
                help="Suggested from the industry. Choose another if a different checklist fits the company better.",
            )]
            if not written_for_industry:
                st.caption(":material/info: There is no checklist written for this industry yet, so the fintech one "
                           "is suggested.")
            if checklist != suggested_checklist:
                st.caption(":material/edit: You chose a different checklist from the one suggested for this industry.")
            st.caption("Industry: replayed, $0.00" if suggestion.replayed
                       else f"Industry: about ${suggestion.cost_usd:.3f}")
    navigation("Next", "industry" in st.session_state, save=lambda: remember(choice=(industry, checklist)))
    if "industry" in st.session_state:
        if source == "Upload documents":
            st.caption(f"Next runs the KYC checks and shows the results: Claude reads every document again against "
                       f"the checklist (roughly 3p per document, about ${len(documents) * 0.027:.2f} for these "
                       f"{len(documents)}). A reopened review with unchanged documents and checklist costs nothing.")
        elif checklist != SAMPLE_CHECKLIST:
            st.caption(":material/payments: The sample's saved answer is for the fintech checklist. With this checklist, "
                       "Next asks Claude to run the checks again (about 20p).")
    st.stop()

if "industry" not in st.session_state or "choice" not in st.session_state:
    go("industry")
suggestion = st.session_state.industry[1]
industry, checklist = st.session_state.choice
suggested_checklist, _ = checklist_for(industry)

# Results no longer match if the labels or the checklist changed
if st.session_state.get("assessment") and st.session_state.assessment[0] != (confirmed, checklist):
    st.session_state.pop("assessment")

# --- Screen 4: results. The checks run as this screen opens, then the results appear ---

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
review_path = case_file(pack_key, checklist)
overrides = load_overrides(review_path)
# The legal entity name rule on check 1.1, then the analyst's changes, which always have the final say
named = apply_entity_name(original, entity_name, parse_company_number(company_link), lookup=cached_company)
result = apply_overrides(named, overrides)

st.header("Results")
st.caption(
    f"Industry: {INDUSTRIES[industry]}. Checklist: {CHECKLISTS[checklist][0]} ({len(result.outcomes)} checks)"
    + (", chosen by you instead of the suggested one." if checklist != suggested_checklist else ".")
    + (f" {len(overrides)} result(s) changed by an analyst." if overrides else "")
)
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
                    "Before the analyst's change": o.before_review,
                }
                for o in outcomes
            ]),
            column_config={
                "Check": st.column_config.TextColumn(width="medium"),
                "Finding": st.column_config.TextColumn(width="large"),
                "Evidence": st.column_config.ListColumn(width="large"),
                "Claude's view": st.column_config.TextColumn(help="Shown when the fixed rules made the decision"),
                "Before the analyst's change": st.column_config.TextColumn(
                    help="The original answer from Claude or the rules, shown when an analyst changed it"),
            },
            hide_index=True,
        )

# --- Analyst review ---

with st.container(border=True):
    st.subheader(":material/rate_review: Review a check")
    st.caption(
        "Change a result once you have looked at the evidence. The original answer is kept beside yours. "
        ":material/lock: Saved on this computer only (the reviews folder), never sent to Claude or committed."
    )
    outcome_by_id = {o.check.id: o for o in result.outcomes}
    with st.form("review", clear_on_submit=True):
        check_id = st.selectbox(
            "Check", list(outcome_by_id),
            format_func=lambda i: f"{i} · {outcome_by_id[i].check.check[:90]} ({outcome_by_id[i].status.value})",
        )
        new_status = Status(st.segmented_control(
            "New status", [s.value for s in STATUS_TEXT], default=Status.PRESENT.value, required=True))
        note = st.text_area("Reason", placeholder="e.g. Client confirmed by email on 22 Oct that Jamie Example holds 25%")
        reviewer = st.text_input("Reviewer", value=st.session_state.get("last_reviewer", ""))
        if st.form_submit_button("Save change", type="primary", icon=":material/save:"):
            try:
                save_override(review_path, named, check_id, new_status, note, reviewer)
            except ValueError as error:
                st.error(str(error), icon=":material/error:")
            else:
                st.session_state.last_reviewer = reviewer.strip()
                st.rerun()

    if overrides:
        st.markdown("**Saved changes**")
    for change in overrides.values():
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(
                f"**{change.check_id}** · {change.original_status.value} → **{change.status.value}** "
                f"by {change.reviewer} on {change.reviewed_on}: {change.note}",
                width="stretch",
            )
            st.button("Undo", key=f"undo_{change.check_id}", icon=":material/undo:",
                      on_click=remove_override, args=(review_path, change.check_id))

navigation()
st.caption(
    "Items marked 🔎 must be reviewed by an analyst. Clario supports, and does not replace, a KYC review. "
    "Not legal advice."
)
