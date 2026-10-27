"""Facts pulled out of client documents, passed from the extractor to the validator."""

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Fact:
    """One piece of information and where it was found, e.g. "Certificate of incorporation p.1".

    value is None when the extractor could not find it. A date that could not be
    understood is kept as the original text so the validator can report it.
    """

    value: str | date | bool | None = None
    source: str = ""


@dataclass(frozen=True)
class CertificateOfIncorporation:
    company_name: Fact = field(default_factory=Fact)
    company_number: Fact = field(default_factory=Fact)
    incorporation_date: Fact = field(default_factory=Fact)


@dataclass(frozen=True)
class ProofOfAddress:
    company_name: Fact = field(default_factory=Fact)
    registered_office: Fact = field(default_factory=Fact)
    document_date: Fact = field(default_factory=Fact)


@dataclass(frozen=True)
class OnboardingQuestionnaire:
    # True = trades from the registered office, False = trades elsewhere, None = not answered
    trades_from_registered_office: Fact = field(default_factory=Fact)
    principal_place_of_business: Fact = field(default_factory=Fact)


@dataclass(frozen=True)
class ArticlesOfAssociation:
    company_name: Fact = field(default_factory=Fact)
    # Short summary of who can act and sign for the company, written by the extractor
    authority_summary: Fact = field(default_factory=Fact)
