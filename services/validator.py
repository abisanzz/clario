"""Decide a status for each KYC checklist item."""

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Callable

from services.companies_house import CompanyNotFound, LookupFailed, get_company
from services.documents import (
    ArticlesOfAssociation,
    CertificateOfIncorporation,
    OnboardingQuestionnaire,
    ProofOfAddress,
)

# UK company numbers are 8 characters: 8 digits, or 2 letters then 6 digits (e.g. SC123456)
COMPANY_NUMBER_PATTERN = re.compile(r"^(\d{8}|[A-Z]{2}\d{6})$")

# Proof of address older than this is treated as out of date. Common KYC practice, not set by the checklist.
PROOF_OF_ADDRESS_MAX_AGE_MONTHS = 3


class Status(Enum):
    """The five statuses used on the checklist spreadsheet, spelled exactly the same."""

    NOT_STARTED = "Not started"
    PRESENT = "Present"
    MISSING = "Missing"
    UNCLEAR = "Unclear"
    NEEDS_HUMAN_REVIEW = "Needs human review"


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one check, mirroring the spreadsheet's Status, Finding and Source reference columns."""

    check_id: str
    status: Status
    finding: str = ""
    source_reference: str = ""

    def __post_init__(self):
        if not isinstance(self.status, Status):
            raise TypeError(f"{self.check_id}: status must be a Status, not {self.status!r}")
        if self.status is not Status.NOT_STARTED and not self.finding.strip():
            raise ValueError(f"{self.check_id}: a '{self.status.value}' result must include a finding")


def _format_date(value: date) -> str:
    return f"{value.day} {value:%b %Y}"


def check_1_1(certificate: CertificateOfIncorporation | None, today: date | None = None) -> CheckResult:
    """Registered name, company number and incorporation date."""
    if certificate is None:
        return CheckResult("1.1", Status.MISSING, "No certificate of incorporation provided")

    today = today or date.today()
    facts = {
        "company name": certificate.company_name,
        "company number": certificate.company_number,
        "incorporation date": certificate.incorporation_date,
    }
    missing = [name for name, fact in facts.items() if fact.value is None or str(fact.value).strip() == ""]
    unclear = []

    number = certificate.company_number.value
    if "company number" not in missing:
        number = re.sub(r"\s", "", str(number)).upper()
        if not COMPANY_NUMBER_PATTERN.match(number):
            problem = f"company number '{number}' is not in the UK 8-character format"
            if number.isdigit() and len(number) < 8:
                problem += "; leading zeros may have been dropped"
            unclear.append(problem)

    incorporated = certificate.incorporation_date.value
    if "incorporation date" not in missing:
        if not isinstance(incorporated, date):
            unclear.append(f"incorporation date '{incorporated}' could not be read as a date")
        elif incorporated > today:
            unclear.append(f"incorporation date {_format_date(incorporated)} is in the future")

    sources = sorted({fact.source for fact in facts.values() if fact.source})
    source_reference = "; ".join(sources)

    if missing:
        finding = "Not found on certificate: " + ", ".join(missing)
        if unclear:
            finding += ". Also: " + "; ".join(unclear)
        return CheckResult("1.1", Status.MISSING, finding, source_reference)
    if unclear:
        finding = "; ".join(unclear)
        return CheckResult("1.1", Status.UNCLEAR, finding[0].upper() + finding[1:], source_reference)

    finding = (
        f"Name '{certificate.company_name.value}', number {number}, "
        f"incorporated {_format_date(incorporated)}"
    )
    return CheckResult("1.1", Status.PRESENT, finding, source_reference)


def _is_blank(value) -> bool:
    return value is None or str(value).strip() == ""


def _months_before(day: date, months: int) -> date:
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def normalise_company_name(name: str) -> str:
    """A company name in a standard form: capitals, no punctuation, single spaces, LTD and PLC."""
    name = re.sub(r"[^\w\s]", " ", name.upper().replace("&", " AND "))
    name = " ".join(name.split())
    name = re.sub(r"\bPUBLIC LIMITED COMPANY\b", "PLC", name)
    return re.sub(r"\bLIMITED\b", "LTD", name)


def _same_company_name(a: str, b: str) -> bool:
    """True if two names differ only in capitals, punctuation, spacing, or LIMITED/LTD and PLC wording."""
    return normalise_company_name(a) == normalise_company_name(b)


def entity_name_matches(entered: str, registered: str) -> bool:
    """True if the legal entity name the user entered is the registered name, allowing for capitals, punctuation,
    spacing and LIMITED/LTD or PLC wording."""
    return bool(entered.strip()) and _same_company_name(entered, registered)


def entity_name_rule(
    entered: str, company_number: str | None, lookup: Callable[[str], dict] = get_company,
) -> tuple[bool | None, str]:
    """Compare the legal entity name the user entered with the name registered at Companies House.

    Returns (True if it matches, False if not, None if it could not be compared) and a note for check 1.1.
    """
    entered = " ".join(entered.split())
    number = re.sub(r"\s", "", company_number or "").upper()
    if not number:
        return None, f"Legal entity name entered ({entered}) not compared: no company number"
    try:
        registered = lookup(number).get("company_name") or ""
    except CompanyNotFound:
        return None, f"Legal entity name entered ({entered}) not compared: company {number} is not on Companies House"
    except LookupFailed as error:
        return None, f"Legal entity name entered ({entered}) not compared: Companies House lookup failed ({error})"
    if entity_name_matches(entered, registered):
        return True, f"Legal entity name entered matches Companies House ({registered})"
    return False, f"Legal entity name entered ({entered}) does not match Companies House ({registered})"


def check_1_2(
    proof: ProofOfAddress | None,
    questionnaire: OnboardingQuestionnaire | None,
    certificate: CertificateOfIncorporation | None = None,
    today: date | None = None,
) -> CheckResult:
    """Registered office and principal place of business, if different."""
    if proof is None:
        return CheckResult("1.2", Status.MISSING, "No proof of registered address provided")

    today = today or date.today()
    questionnaire = questionnaire or OnboardingQuestionnaire()
    missing = []
    unclear = []

    if _is_blank(proof.registered_office.value):
        missing.append("Registered office address not found on proof of address")

    document_date = proof.document_date.value
    if _is_blank(document_date):
        unclear.append("proof of address has no date, so its age cannot be confirmed")
    elif not isinstance(document_date, date):
        unclear.append(f"proof of address date '{document_date}' could not be read as a date")
    elif document_date > today:
        unclear.append(f"proof of address is dated in the future ({_format_date(document_date)})")
    elif document_date < _months_before(today, PROOF_OF_ADDRESS_MAX_AGE_MONTHS):
        unclear.append(
            f"proof of address is dated {_format_date(document_date)}, "
            f"more than {PROOF_OF_ADDRESS_MAX_AGE_MONTHS} months ago"
        )

    proof_name = proof.company_name.value
    certificate_name = certificate.company_name.value if certificate else None
    if _is_blank(proof_name):
        unclear.append("company name not found on proof of address, so it cannot be matched to the client")
    elif not _is_blank(certificate_name) and not _same_company_name(str(proof_name), str(certificate_name)):
        unclear.append(f"proof of address is for '{proof_name}', certificate says '{certificate_name}'")

    trades_from_registered_office = questionnaire.trades_from_registered_office.value
    principal = questionnaire.principal_place_of_business.value
    if trades_from_registered_office is True:
        principal_text = "same as registered office"
    elif trades_from_registered_office is False and not _is_blank(principal):
        principal_text = str(principal)
    elif trades_from_registered_office is False:
        principal_text = None
        unclear.append("client operates away from the registered office but gave no principal place of business")
    else:
        principal_text = None
        unclear.append("not stated whether the principal place of business differs from the registered office")

    facts = [
        proof.company_name, proof.registered_office, proof.document_date,
        questionnaire.trades_from_registered_office, questionnaire.principal_place_of_business,
    ]
    source_reference = "; ".join(sorted({fact.source for fact in facts if fact.source}))

    if missing:
        finding = "; ".join(missing)
        if unclear:
            finding += ". Also: " + "; ".join(unclear)
        return CheckResult("1.2", Status.MISSING, finding, source_reference)
    if unclear:
        finding = "; ".join(unclear)
        return CheckResult("1.2", Status.UNCLEAR, finding[0].upper() + finding[1:], source_reference)

    finding = f"Registered office: {proof.registered_office.value}. Principal place of business: {principal_text}"
    return CheckResult("1.2", Status.PRESENT, finding, source_reference)


def check_1_4(
    articles: ArticlesOfAssociation | None,
    certificate: CertificateOfIncorporation | None = None,
) -> CheckResult:
    """Constitution and who has power to bind the company. Never Present: authority is a judgement call."""
    if articles is None:
        return CheckResult("1.4", Status.MISSING, "No articles of association provided")

    summary = articles.authority_summary
    if _is_blank(summary.value):
        authority = "no description of signing authority was found; analyst to read the articles"
    else:
        where = f" ({summary.source})" if summary.source else ""
        authority = f"authority{where}: {summary.value}"

    articles_name = articles.company_name.value
    certificate_name = certificate.company_name.value if certificate else None
    problem = None
    if _is_blank(articles_name):
        problem = "Company name not found on articles, so they cannot be matched to the client"
    elif not _is_blank(certificate_name) and not _same_company_name(str(articles_name), str(certificate_name)):
        problem = f"Articles are for '{articles_name}', certificate says '{certificate_name}'"

    source_reference = "; ".join(sorted({f.source for f in (articles.company_name, summary) if f.source}))

    if problem:
        return CheckResult("1.4", Status.UNCLEAR, f"{problem}. Also: {authority}", source_reference)
    if _is_blank(summary.value):
        return CheckResult("1.4", Status.NEEDS_HUMAN_REVIEW, f"Articles provided but {authority}", source_reference)
    return CheckResult(
        "1.4",
        Status.NEEDS_HUMAN_REVIEW,
        f"Articles provided. {authority[0].upper() + authority[1:]}. Analyst to confirm who can bind the company",
        source_reference,
    )


def _format_companies_house_date(value) -> str:
    """Companies House dates look like '2027-06-30'; show them as '30 Jun 2027'."""
    try:
        return _format_date(datetime.strptime(str(value), "%Y-%m-%d").date())
    except ValueError:
        return str(value) if value else "date not shown"


def check_1_3(
    certificate: CertificateOfIncorporation | None,
    lookup: Callable[[str], dict] = get_company,
    today: date | None = None,
) -> CheckResult:
    """Company status is active, with accounts and confirmation statement up to date."""
    number = certificate.company_number.value if certificate else None
    if _is_blank(number):
        return CheckResult("1.3", Status.MISSING, "No company number to look up")

    today = today or date.today()
    number = re.sub(r"\s", "", str(number)).upper()
    source_reference = f"Companies House API, checked {_format_date(today)}"

    try:
        record = lookup(number)
    except CompanyNotFound:
        return CheckResult(
            "1.3", Status.UNCLEAR,
            f"Company number {number} not found at Companies House; check for a typo", source_reference,
        )
    except LookupFailed as error:
        return CheckResult(
            "1.3", Status.NEEDS_HUMAN_REVIEW,
            f"Companies House lookup failed ({error}); check manually", source_reference,
        )

    accounts = record.get("accounts") or {}
    confirmation = record.get("confirmation_statement") or {}
    accounts_due = _format_companies_house_date(accounts.get("next_due"))
    confirmation_due = _format_companies_house_date(confirmation.get("next_due"))

    red_flags = []
    status = record.get("company_status") or "not shown"
    if status != "active":
        detail = record.get("company_status_detail")
        red_flags.append(f"Companies House status: {status}" + (f" ({detail})" if detail else ""))
    if accounts.get("overdue"):
        red_flags.append(f"accounts overdue (were due {accounts_due})")
    if confirmation.get("overdue"):
        red_flags.append(f"confirmation statement overdue (was due {confirmation_due})")

    # Does the register agree with the certificate?
    mismatches = []
    compared = []
    certificate_name = certificate.company_name.value
    register_name = record.get("company_name")
    if not _is_blank(certificate_name) and not _is_blank(register_name):
        compared.append("name")
        if not _same_company_name(str(certificate_name), str(register_name)):
            mismatches.append(
                f"name on certificate '{certificate_name}' does not match Companies House '{register_name}'"
            )
    certificate_date = certificate.incorporation_date.value
    register_date = record.get("date_of_creation")
    if isinstance(certificate_date, date) and register_date:
        compared.append("incorporation date")
        if _format_companies_house_date(register_date) != _format_date(certificate_date):
            mismatches.append(
                f"incorporation date on certificate {_format_date(certificate_date)} does not match "
                f"Companies House {_format_companies_house_date(register_date)}"
            )

    if red_flags or mismatches:
        finding = "; ".join(red_flags + mismatches)
        status = Status.NEEDS_HUMAN_REVIEW if red_flags else Status.UNCLEAR
        return CheckResult("1.3", status, finding[0].upper() + finding[1:], source_reference)

    finding = (
        f"Active at Companies House. Accounts next due {accounts_due}; "
        f"confirmation statement next due {confirmation_due}"
    )
    if compared:
        verb = "match" if len(compared) > 1 else "matches"
        finding += f". {' and '.join(compared).capitalize()} {verb} the certificate"
    return CheckResult("1.3", Status.PRESENT, finding, source_reference)
