"""Decide a status for each KYC checklist item."""

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum

from services.documents import CertificateOfIncorporation

# UK company numbers are 8 characters: 8 digits, or 2 letters then 6 digits (e.g. SC123456)
COMPANY_NUMBER_PATTERN = re.compile(r"^(\d{8}|[A-Z]{2}\d{6})$")


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
    """Registered name, company number, incorporation date and legal form."""
    if certificate is None:
        return CheckResult("1.1", Status.MISSING, "No certificate of incorporation provided")

    today = today or date.today()
    facts = {
        "company name": certificate.company_name,
        "company number": certificate.company_number,
        "incorporation date": certificate.incorporation_date,
        "legal form": certificate.legal_form,
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
        f"incorporated {_format_date(incorporated)}, legal form '{certificate.legal_form.value}'"
    )
    return CheckResult("1.1", Status.PRESENT, finding, source_reference)
