"""Facts pulled out of client documents, passed from the extractor to the validator."""

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Fact:
    """One piece of information and where it was found, e.g. "Certificate of incorporation p.1".

    value is None when the extractor could not find it. A date that could not be
    understood is kept as the original text so the validator can report it.
    """

    value: str | date | None = None
    source: str = ""


@dataclass(frozen=True)
class CertificateOfIncorporation:
    company_name: Fact = field(default_factory=Fact)
    company_number: Fact = field(default_factory=Fact)
    incorporation_date: Fact = field(default_factory=Fact)
    legal_form: Fact = field(default_factory=Fact)
