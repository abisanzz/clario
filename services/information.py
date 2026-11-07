"""What one checklist line rests on, for its Details on Evidence review: what the documents say, what the public
registers and website said, and what the analyst provided. Plain text: the screen adds the formatting. A rule, so it
costs nothing."""

import re
from typing import NamedTuple

from services.intelligence import key_facts, normalise, owners, people
from services.pack import DocumentDetails

PUBLIC_SOURCES = ("Companies House record", "FCA register record", "Company website")
# The facts compared across documents on Document intelligence, and the line each belongs to, with its label there
KEY_FACT_LINES = {"1.1": {"Company name": "Company name", "Registration number": "Company number"},
                  "1.2": {"Registered address": "Registered office"}}


class Row(NamedTuple):
    """One value from the documents and everywhere it was found, e.g. ("Company name", "EXAMPLE PAYMENTS LTD",
    ["certificate.pdf, page 1", "articles.pdf"], False)."""
    label: str
    value: str
    sources: list[str]
    disagree: bool = False  # other documents give a different value


def where(source: str) -> str:
    """ "certificate.pdf p.1" -> "certificate.pdf, page 1" """
    return re.sub(r" p\.(\d+)$", r", page \1", source)


def without_page(source: str) -> str:
    return re.sub(r", page \d+$", "", source)


def from_documents_and_registers(check_id: str, section: str, line_facts: list[tuple[str, str, str]],
                                 details: dict[str, DocumentDetails], evidence: list[str],
                                 document_names: set[str]) -> tuple[list[Row], list[str]]:
    """The documents' values for one line, one row per value, so a value found in several documents (or quoted from
    several) is one row listing them all; and what the public registers and website said, one line each.

    `line_facts` are the labelled facts the rules read for the line; `details` what Document intelligence extracted
    from each document; `evidence` the line's quotes, as "source p.N: \"quote\"" or a reference the rules added."""
    rows: dict[tuple[str, str], Row] = {}

    def add(label: str, value: str, source: str, disagree: bool = False) -> None:
        row = rows.setdefault((label, normalise(value)), Row(label, value, [], disagree))
        if source in row.sources or any(without_page(listed) == source for listed in row.sources):
            return  # already listed (with its page)
        if source != without_page(source) and without_page(source) in row.sources:
            row.sources[row.sources.index(without_page(source))] = source  # now with its page
            return
        row.sources.append(source)

    for fact in key_facts(details):
        label = KEY_FACT_LINES.get(check_id, {}).get(fact.fact)
        for value, found_in in (fact.values.items() if label else []):
            for name in found_in:
                add(label, value, name, fact.disagree)
    for label, value, source in line_facts:
        add(label, value, where(source))
    if section.startswith("3."):
        for name, shares in owners(details):
            for share, found_in in shares.items():
                for document in found_in:
                    add(f"Owner {name}", share, document, len(shares) > 1)
    if section.startswith("4."):
        for name, roles, found_in in people(details):
            for document in found_in:
                add(f"Person {name}", ", ".join(roles) or "named", document)
    registers = []
    for item in evidence:
        quoted = re.match(r'^(.*?)(?: p\.(\d+))?: "(.*)"$', item, re.S)
        if not quoted:  # a reference the rules added, e.g. "Companies House API, checked 07 Nov 2026"
            if not any(item.startswith(name) for name in document_names):  # a document is listed above
                registers.append(item)
            continue
        source, page, quote = quoted.groups()
        if source in PUBLIC_SOURCES:  # a register or website has no pages
            registers.append(f"“{quote}” · {source}")
        else:  # a quote that is a value already listed joins that row, e.g. the company name on the certificate
            same = next((row for (label, value), row in rows.items()
                         if label != "Quoted" and value == normalise(quote)), None)
            add(same.label if same else "Quoted", same.value if same else quote,
                f"{source}, page {page}" if page else source, same.disagree if same else False)
    return list(rows.values()), registers


def provided_by_analyst(check_id: str, evidence_source: str, entity_name: str, company_number: str, fca_frn: str,
                        website: str, supporting: list[dict]) -> list[tuple[str, str, str]]:
    """What the analyst entered or added that the line relies on: (label, value, note), e.g. ("Company number
    entered", "99999901", "")."""
    provided = []
    if check_id == "1.1" and entity_name.strip():
        provided.append(("Legal entity name entered", entity_name.strip(), ""))
    if check_id in ("1.1", "1.3") and company_number.strip():
        provided.append(("Company number entered", company_number.strip(), ""))
    if "FCA" in evidence_source and fca_frn.strip():
        provided.append(("FCA firm reference number entered", fca_frn.strip(), ""))
    if "website" in evidence_source.lower() and website.strip():
        provided.append(("Website entered", website.strip(), ""))
    for record in supporting:
        provided.append(("Supporting document", record["name"],
                         (f"({record['description']}) " if record.get("description") else "")
                         + "added" + (f" by {record['added_by']}" if record.get("added_by") else "")
                         + f" on {record['added_on']}"
                         + (f". Clario AI: {record['verdict']}. {record.get('verdict_finding', '')}"
                            if record.get("verdict") else "")))
    return provided
