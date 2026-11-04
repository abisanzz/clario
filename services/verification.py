"""Extraction, cross-document checks and external verification, kept apart.

For each key fact: what each document says (extracted), whether the documents agree (cross-checked), and whether a
trusted external source confirms it (externally verified). Only a live lookup of the Companies House or FCA register
counts as external verification. Documents the customer supplied, including ones that look like register extracts,
never do. Internal consistency is never described as verification.
"""

import re
from dataclasses import dataclass, field

from services.intelligence import key_facts, normalise, owners, people
from services.pack import DocumentDetails

NOT_VERIFIED = "Not externally verified"
COMPANIES_HOUSE, FCA_REGISTER = "Companies House", "FCA register"
TITLES = {"mr", "mrs", "ms", "miss", "dr", "sir", "dame", "lord", "lady", "prof"}


@dataclass(frozen=True)
class RegisterRecord:
    """What a live Companies House lookup returned, reduced to the facts Clario compares."""

    company_name: str
    company_number: str
    address: str
    postcode: str
    directors: list[str] = field(default_factory=list)  # active directors
    owners: list[str] = field(default_factory=list)  # active persons with significant control


@dataclass(frozen=True)
class FactCheck:
    fact: str  # e.g. "Company name"
    extracted: str  # what the documents say
    found_in: list[str]  # the documents it was extracted from
    cross_check: str  # e.g. "Consistent across 4 documents"
    consistent: bool
    external: str  # "Verified against Companies House", a mismatch, or "Not externally verified"
    externally_verified: bool = False
    assessment: str = ""  # one sentence for the analyst


def _person(name: str) -> str:
    """A person's name for comparison: "HART, Amelia Jane" and "Mrs Amelia Hart" both become "amelia hart"."""
    if "," in name:
        surname, _, forenames = name.partition(",")
        name = f"{forenames} {surname}"
    words = [w for w in re.sub(r"[^\w\s]", " ", name.casefold()).split() if w not in TITLES]
    return " ".join(sorted({words[0], words[-1]})) if words else ""


def _number(value: str) -> str:
    return re.sub(r"\s", "", value).upper().lstrip("0")


def companies_house_record(company_number: str | None, get_company, get_officers, get_owners) -> RegisterRecord | None:
    """The live Companies House record, or None when there is no number, the company isn't there or the lookup
    failed. Lookup functions are passed in so the app can use its cached versions."""
    if not company_number:
        return None
    try:
        profile = get_company(company_number)
        officers = get_officers(company_number)
        controllers = get_owners(company_number)
    except Exception:  # not found or the lookup failed: nothing is verified
        return None
    address = profile.get("registered_office_address") or {}
    return RegisterRecord(
        profile.get("company_name", ""), profile.get("company_number", company_number),
        ", ".join(str(address[k]) for k in ("address_line_1", "address_line_2", "locality", "postal_code")
                  if address.get(k)),
        str(address.get("postal_code", "")),
        [o.get("name", "") for o in officers if "director" in o.get("officer_role", "") and not o.get("resigned_on")],
        [p.get("name", "") for p in controllers if not p.get("ceased_on")])


def _cross(values: dict[str, list[str]]) -> tuple[str, bool]:
    documents = sorted({d for found in values.values() for d in found})
    if len(values) > 1:
        return "Documents disagree", False
    if len(documents) == 1:
        return "Found in one document", True
    return f"Consistent across {len(documents)} documents", True


def _assessment(consistent: bool, external: str, verified: bool) -> str:
    if verified:
        return f"Confirmed by a live {external.removeprefix('Verified against ').split(' (')[0]} check."
    if not consistent:
        return "The documents disagree; resolve the difference with the client."
    if external != NOT_VERIFIED:
        return "The documents agree with each other but not with the public register; investigate."
    return "Internally consistent, but external verification remains outstanding."


def _single(fact: str, values: dict[str, list[str]], external: str, verified: bool) -> FactCheck:
    cross, consistent = _cross(values)
    found_in = sorted({d for found in values.values() for d in found})
    return FactCheck(fact, " / ".join(values), found_in, cross, consistent, external, verified,
                     _assessment(consistent, external, verified))


def check_facts(details: dict[str, DocumentDetails], register: RegisterRecord | None = None,
                fca_status: str = "") -> list[FactCheck]:
    """Each key fact with its extraction, cross-document check and external verification, kept separate.
    fca_status is the firm's status from a live FCA register lookup ("" if none was made)."""
    checks = []
    for fact in key_facts(details):
        values = fact.values
        external, verified = NOT_VERIFIED, False
        if register:
            wanted = {"Company name": (normalise(register.company_name), normalise),
                      "Registration number": (_number(register.company_number), _number)}.get(fact.fact)
            if wanted:
                target, clean = wanted
                if all(clean(value) == target for value in values):
                    external, verified = f"Verified against {COMPANIES_HOUSE}", True
                else:
                    external = f"Does not match {COMPANIES_HOUSE} ({register.company_name if fact.fact == 'Company name' else register.company_number})"
            elif fact.fact == "Registered address":
                postcode = normalise(register.postcode).replace(" ", "")
                if postcode and all(postcode in normalise(value).replace(" ", "") for value in values):
                    external, verified = f"Verified against {COMPANIES_HOUSE} (postcode matches)", True
                else:
                    external = f"Does not match {COMPANIES_HOUSE} ({register.address})"
        checks.append(_single(fact.fact, values, external, verified))

    named = people(details)
    directors = [(name, found_in) for name, roles, found_in in named if any("director" in r.casefold() for r in roles)]
    if directors:
        documents = sorted({d for _, found_in in directors for d in found_in})
        external, verified = NOT_VERIFIED, False
        if register:
            on_register = {_person(n) for n in register.directors}
            missing = [n for n, _ in directors if _person(n) not in on_register]
            external, verified = ((f"Verified against {COMPANIES_HOUSE}", True) if not missing
                                  else (f"Not on {COMPANIES_HOUSE} as directors: {', '.join(missing)}", False))
        checks.append(_single("Directors", {", ".join(n for n, _ in directors): documents}, external, verified))

    owned = owners(details)
    if owned:
        disagree = any(len(shares) > 1 for _, shares in owned)
        summary = "; ".join(f"{name} {' / '.join(shares)}" for name, shares in owned)
        documents = sorted({d for _, shares in owned for found in shares.values() for d in found})
        external, verified = NOT_VERIFIED, False
        if register:
            on_register = {_person(n) for n in register.owners}
            missing = [name for name, _ in owned if _person(name) not in on_register]
            external, verified = ((f"Verified against {COMPANIES_HOUSE} (persons with significant control)", True)
                                  if not missing else (f"Not on the {COMPANIES_HOUSE} PSC register: {', '.join(missing)}",
                                                       False))
        if disagree:
            cross = "Documents disagree on the shares"
        else:
            cross = "Found in one document" if len(documents) == 1 else f"Consistent across {len(documents)} documents"
        checks.append(FactCheck("Ownership", summary, documents, cross, not disagree, external, verified,
                                _assessment(not disagree, external, verified)))

    if fca_status:
        checks.append(FactCheck("FCA regulatory status", fca_status, [], "Checked on the live register", True,
                                f"Verified against the {FCA_REGISTER}", True,
                                f"The live FCA register shows the firm as {fca_status}."))
    else:
        checks.append(FactCheck("FCA regulatory status", "", [], "Not checked", True, NOT_VERIFIED, False,
                                "No live FCA register check has been made; a regulatory status shown in the "
                                "customer's documents is not independent evidence."))
    return checks
