"""Key facts across a company's documents: the details Claude extracted from each one, side by side, with the facts
the documents disagree on flagged for the analyst. A rule, so it costs nothing."""

import re
from dataclasses import dataclass

from services.pack import DocumentDetails

FACTS = {"company_name": "Company name", "registration_number": "Registration number",
         "registered_address": "Registered address"}


def normalise(value: str) -> str:
    """Ignore differences in case, spacing, punctuation and "Limited" vs "Ltd"."""
    value = re.sub(r"[^\w\s]", " ", value.casefold())
    value = re.sub(r"\blimited\b", "ltd", value)
    value = re.sub(r"\bpublic limited company\b", "plc", value)
    return " ".join(value.split()).lstrip("0") if value.replace(" ", "").isdigit() else " ".join(value.split())


@dataclass(frozen=True)
class KeyFact:
    fact: str  # e.g. "Company name"
    values: dict[str, list[str]]  # each value as first printed -> the documents that show it

    @property
    def disagree(self) -> bool:
        return len(self.values) > 1


def is_firm_reference(value: str) -> bool:
    """An FCA firm reference number given as a "registration number": it isn't a company number, so it is left out
    when company numbers are compared."""
    return "FRN" in value.upper().replace(" ", "")


def key_facts(details: dict[str, DocumentDetails]) -> list[KeyFact]:
    """For the company name, registration number and registered address: what each document says."""
    facts = []
    for attribute, title in FACTS.items():
        values, printed = {}, {}
        for name, found in details.items():
            value = getattr(found, attribute)
            if value and not (attribute == "registration_number" and is_firm_reference(value)):
                key = normalise(value)
                printed.setdefault(key, value)
                values.setdefault(printed[key], []).append(name)
        if values:
            facts.append(KeyFact(title, values))
    return facts


def people(details: dict[str, DocumentDetails]) -> list[tuple[str, list[str], list[str]]]:
    """Everyone named with a role: (name, roles, documents), in the order first found."""
    found: dict[str, tuple[str, list[str], list[str]]] = {}
    for document, d in details.items():
        for name, role in d.people:
            entry = found.setdefault(normalise(name), (name, [], []))
            if role and role not in entry[1]:
                entry[1].append(role)
            if document not in entry[2]:
                entry[2].append(document)
    return list(found.values())


def percentage(share: str) -> str:
    """The percentage in a share as printed, e.g. "600 ordinary shares (60%)" -> "60%"; "" if none is given."""
    found = re.search(r"(\d+(?:\.\d+)?)\s*%", share)
    return f"{float(found.group(1)):g}%" if found else ""


def owners(details: dict[str, DocumentDetails]) -> list[tuple[str, dict[str, list[str]]]]:
    """Each owner with the share each document gives them: (name, {share: documents}). Shares are compared by their
    percentage where one is given, so "60%" and "600 ordinary shares (60%)" agree."""
    found: dict[str, tuple[str, dict[str, list[str]]]] = {}
    for document, d in details.items():
        for name, share in d.owners:
            entry = found.setdefault(normalise(name), (name, {}))
            entry[1].setdefault(percentage(share) or share or "share not stated", []).append(document)
    return list(found.values())
