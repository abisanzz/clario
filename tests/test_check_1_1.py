from dataclasses import replace
from datetime import date

import pytest

from services.documents import CertificateOfIncorporation, Fact
from services.validator import Status, check_1_1

TODAY = date(2026, 10, 4)
PAGE_1 = "Certificate of incorporation p.1"


def certificate(**changes):
    """A complete, valid made-up certificate; pass changes to break one part of it."""
    good = CertificateOfIncorporation(
        company_name=Fact("EXAMPLE PAYMENTS LTD", PAGE_1),
        company_number=Fact("12345678", PAGE_1),
        incorporation_date=Fact(date(2019, 3, 14), PAGE_1),
    )
    return replace(good, **changes)


def test_complete_certificate_is_present():
    result = check_1_1(certificate(), today=TODAY)
    assert result.check_id == "1.1"
    assert result.status is Status.PRESENT
    assert result.finding == (
        "Name 'EXAMPLE PAYMENTS LTD', number 12345678, incorporated 14 Mar 2019"
    )
    assert result.source_reference == PAGE_1


def test_no_certificate_is_missing():
    result = check_1_1(None, today=TODAY)
    assert result.status is Status.MISSING
    assert result.finding == "No certificate of incorporation provided"


@pytest.mark.parametrize("field, label", [
    ("company_name", "company name"),
    ("company_number", "company number"),
    ("incorporation_date", "incorporation date"),
])
@pytest.mark.parametrize("empty", [None, "", "   "])
def test_each_missing_fact_is_reported(field, label, empty):
    result = check_1_1(certificate(**{field: Fact(empty)}), today=TODAY)
    assert result.status is Status.MISSING
    assert result.finding == f"Not found on certificate: {label}"


def test_several_missing_facts_are_all_listed():
    result = check_1_1(certificate(company_number=Fact(), incorporation_date=Fact()), today=TODAY)
    assert result.finding == "Not found on certificate: company number, incorporation date"


@pytest.mark.parametrize("number", ["12345678", "SC123456", "sc 123 456", "OC000001", "00445790"])
def test_valid_company_numbers_are_accepted(number):
    assert check_1_1(certificate(company_number=Fact(number, PAGE_1)), today=TODAY).status is Status.PRESENT


@pytest.mark.parametrize("number", ["1234567X", "123456789", "S1234567", "SC12345", "ABC12345"])
def test_badly_formatted_company_number_is_unclear(number):
    result = check_1_1(certificate(company_number=Fact(number, PAGE_1)), today=TODAY)
    assert result.status is Status.UNCLEAR
    assert "is not in the UK 8-character format" in result.finding
    assert "leading zeros" not in result.finding


def test_short_number_hints_at_dropped_leading_zeros():
    result = check_1_1(certificate(company_number=Fact("445790", PAGE_1)), today=TODAY)
    assert result.status is Status.UNCLEAR
    assert result.finding == (
        "Company number '445790' is not in the UK 8-character format; leading zeros may have been dropped"
    )


def test_future_incorporation_date_is_unclear():
    result = check_1_1(certificate(incorporation_date=Fact(date(2030, 1, 1), PAGE_1)), today=TODAY)
    assert result.status is Status.UNCLEAR
    assert result.finding == "Incorporation date 1 Jan 2030 is in the future"


def test_incorporated_today_is_fine():
    assert check_1_1(certificate(incorporation_date=Fact(TODAY, PAGE_1)), today=TODAY).status is Status.PRESENT


def test_unreadable_date_is_unclear():
    result = check_1_1(certificate(incorporation_date=Fact("14th of Marhc", PAGE_1)), today=TODAY)
    assert result.status is Status.UNCLEAR
    assert result.finding == "Incorporation date '14th of Marhc' could not be read as a date"


def test_missing_wins_over_unclear_but_both_are_reported():
    result = check_1_1(
        certificate(company_name=Fact(), company_number=Fact("445790", PAGE_1)), today=TODAY
    )
    assert result.status is Status.MISSING
    assert result.finding.startswith("Not found on certificate: company name. Also: company number '445790'")


def test_sources_from_different_pages_are_all_listed():
    result = check_1_1(
        certificate(incorporation_date=Fact(date(2019, 3, 14), "Certificate of incorporation p.2")),
        today=TODAY,
    )
    assert result.source_reference == "Certificate of incorporation p.1; Certificate of incorporation p.2"
