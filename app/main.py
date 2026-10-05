"""Clario web page: read a certificate of incorporation and show the Section 1 KYC checks.

Run from the project folder:  .venv/bin/streamlit run app/main.py
"""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))  # so "services" can be imported when Streamlit runs this file

from services.checklist import load_checks  # noqa: E402
from services.extractor import ExtractionFailed, read_certificate  # noqa: E402
from services.validator import CheckResult, Status, check_1_1, check_1_3  # noqa: E402

SAMPLE_PDF = PROJECT_ROOT / "sample_documents" / "certificate_of_incorporation.pdf"
SAMPLE_ANSWER = PROJECT_ROOT / "sample_documents" / "certificate_of_incorporation.answer.json"

ICONS = {
    Status.PRESENT: "✅",
    Status.MISSING: "❌",
    Status.UNCLEAR: "⚠️",
    Status.NEEDS_HUMAN_REVIEW: "🔎",
    Status.NOT_STARTED: "⏳",
}
WAITING_FOR = {
    "1.2": "Needs a proof of address and the onboarding questionnaire (coming next)",
    "1.4": "Needs the articles of association (coming next)",
}

st.set_page_config(page_title="Clario KYC check", page_icon="🔎", layout="wide")
st.title("Clario: KYC document check")
st.write(
    "Upload a UK **certificate of incorporation**. Claude reads it, then fixed rules check it against "
    "the KYC checklist and the live Companies House register. Every result says why, and where it came from."
)

choice = st.radio("Document", ["Use the sample certificate", "Upload a PDF"], horizontal=True)
if choice == "Use the sample certificate":
    st.caption("A fictitious specimen for EXAMPLE PAYMENTS LTD. Its company number belongs to a real, dissolved company.")
    pdf_bytes, saved_answer = SAMPLE_PDF.read_bytes(), SAMPLE_ANSWER
else:
    upload = st.file_uploader("Certificate of incorporation (PDF)", type=["pdf"])
    st.caption("Only upload fictitious or approved documents: the file is sent to Anthropic to be read.")
    pdf_bytes, saved_answer = (upload.getvalue() if upload else None), None

if not st.button("Check document", type="primary", disabled=pdf_bytes is None):
    st.stop()

with st.spinner("Reading the document with Claude and checking Companies House..."):
    try:
        extraction = read_certificate(pdf_bytes, saved_answer=saved_answer)
    except ExtractionFailed as error:
        st.error(f"Could not read the document: {error}.")
        st.stop()
    certificate = extraction.certificate
    results = {r.check_id: r for r in (check_1_1(certificate), check_1_3(certificate))}

st.subheader("What Claude found")
st.dataframe(
    [
        {"Fact": label, "Value": "" if fact.value is None else str(fact.value), "Found on": fact.source or "not found"}
        for label, fact in [
            ("Company name", certificate.company_name),
            ("Company number", certificate.company_number),
            ("Incorporation date", certificate.incorporation_date),
            ("Legal form", certificate.legal_form),
        ]
    ],
    hide_index=True,
    width="stretch",
)

st.subheader("Section 1: Legal existence")
rows = []
for check in load_checks():
    if check.section != "1. Legal existence":
        continue
    result = results.get(check.id, CheckResult(check.id, Status.NOT_STARTED))
    rows.append({
        "ID": check.id,
        "Check": check.check,
        "Status": f"{ICONS[result.status]} {result.status.value}",
        "Finding": result.finding or WAITING_FOR.get(check.id, ""),
        "Source": result.source_reference,
    })
st.dataframe(rows, hide_index=True, width="stretch")

if extraction.replayed:
    st.caption("Cost of this run: $0.00 (saved answer replayed; Companies House checked live).")
else:
    st.caption(
        f"Cost of this run: about ${extraction.cost_usd:.3f} "
        f"({extraction.input_tokens:,} input + {extraction.output_tokens:,} output tokens)."
    )
st.caption("Decisions marked 🔎 must be reviewed by an analyst. This tool supports, and does not replace, a KYC review.")
