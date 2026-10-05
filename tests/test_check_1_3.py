from datetime import date

import pytest

from services.companies_house import CompanyNotFound, LookupFailed
from services.documents import CertificateOfIncorporation, Fact
from services.validator import Status, check_1_3

TODAY = date(2026, 10, 5)
SOURCE = "Companies House API, checked 5 Oct 2026"


def certificate(number="12345678"):
    return CertificateOfIncorporation(company_number=Fact(number, "Certificate of incorporation p.1"))


def record(status="active", accounts_overdue=False, confirmation_overdue=False, **extra):
    """A saved example Companies House record, shaped like the real API's reply."""
    return {
        "company_name": "EXAMPLE PAYMENTS LTD",
        "company_status": status,
        "accounts": {"next_due": "2027-06-30", "overdue": accounts_overdue},
        "confirmation_statement": {"next_due": "2027-03-14", "overdue": confirmation_overdue},
        **extra,
    }


def returns(reply):
    """A fake connector that always gives back this record, and remembers what it was asked."""
    def lookup(number):
        lookup.asked.append(number)
        return reply
    lookup.asked = []
    return lookup


def raises(error):
    def lookup(number):
        raise error
    return lookup


def run(cert, lookup):
    return check_1_3(cert, lookup=lookup, today=TODAY)


# --- Present ---

def test_active_and_up_to_date_is_present():
    result = run(certificate(), returns(record()))
    assert result.check_id == "1.3"
    assert result.status is Status.PRESENT
    assert result.finding == (
        "Active at Companies House. Accounts next due 30 Jun 2027; confirmation statement next due 14 Mar 2027"
    )
    assert result.source_reference == SOURCE


def test_number_is_tidied_before_lookup():
    lookup = returns(record())
    run(certificate("sc 123456"), lookup)
    assert lookup.asked == ["SC123456"]


def test_missing_due_dates_are_handled():
    reply = {"company_status": "active", "accounts": {}, "confirmation_statement": {}}
    result = run(certificate(), returns(reply))
    assert result.status is Status.PRESENT
    assert result.finding.endswith("Accounts next due date not shown; confirmation statement next due date not shown")


# --- Missing ---

@pytest.mark.parametrize("cert", [None, certificate(None), certificate("  ")])
def test_no_company_number_is_missing(cert):
    lookup = returns(record())
    result = run(cert, lookup)
    assert result.status is Status.MISSING
    assert result.finding == "No company number to look up"
    assert lookup.asked == []


# --- Unclear ---

def test_number_not_found_is_unclear():
    result = run(certificate(), raises(CompanyNotFound("12345678")))
    assert result.status is Status.UNCLEAR
    assert result.finding == "Company number 12345678 not found at Companies House; check for a typo"
    assert result.source_reference == SOURCE


# --- Needs human review: red flags ---

@pytest.mark.parametrize("status", ["dissolved", "liquidation", "administration", "receivership", None])
def test_not_active_needs_human_review(status):
    result = run(certificate(), returns(record(status=status)))
    assert result.status is Status.NEEDS_HUMAN_REVIEW
    assert result.finding == f"Companies House status: {status or 'not shown'}"


def test_status_detail_is_included():
    reply = record(status="active", company_status_detail="active-proposal-to-strike-off")
    result = run(certificate(), returns(reply))
    assert result.status is Status.PRESENT  # detail only shown when status is not active

    reply = record(status="dissolved", company_status_detail="converted-to-plc")
    assert run(certificate(), returns(reply)).finding == "Companies House status: dissolved (converted-to-plc)"


def test_accounts_overdue_needs_human_review():
    result = run(certificate(), returns(record(accounts_overdue=True)))
    assert result.status is Status.NEEDS_HUMAN_REVIEW
    assert result.finding == "Accounts overdue (were due 30 Jun 2027)"


def test_confirmation_statement_overdue_needs_human_review():
    result = run(certificate(), returns(record(confirmation_overdue=True)))
    assert result.status is Status.NEEDS_HUMAN_REVIEW
    assert result.finding == "Confirmation statement overdue (was due 14 Mar 2027)"


def test_all_red_flags_are_listed_together():
    result = run(certificate(), returns(record("liquidation", accounts_overdue=True, confirmation_overdue=True)))
    assert result.finding == (
        "Companies House status: liquidation; accounts overdue (were due 30 Jun 2027); "
        "confirmation statement overdue (was due 14 Mar 2027)"
    )


# --- Needs human review: lookup failed ---

@pytest.mark.parametrize("reason", [
    "no Companies House API key set in .env",
    "API key was rejected",
    "no response from Companies House",
])
def test_failed_lookup_needs_human_review(reason):
    result = run(certificate(), raises(LookupFailed(reason)))
    assert result.status is Status.NEEDS_HUMAN_REVIEW
    assert result.finding == f"Companies House lookup failed ({reason}); check manually"


@pytest.mark.parametrize("lookup", [
    returns(record("dissolved")),
    returns(record(accounts_overdue=True)),
    raises(LookupFailed("no response from Companies House")),
    raises(CompanyNotFound("12345678")),
])
def test_red_flags_and_failures_are_never_present(lookup):
    assert run(certificate(), lookup).status is not Status.PRESENT


# --- Comparing the register with the certificate ---

def full_certificate(name="EXAMPLE PAYMENTS LTD", incorporated=date(2019, 3, 14)):
    page = "Certificate of incorporation p.1"
    return CertificateOfIncorporation(
        company_name=Fact(name, page),
        company_number=Fact("12345678", page),
        incorporation_date=Fact(incorporated, page),
    )


def register(**changes):
    return record(**{"company_name": "EXAMPLE PAYMENTS LIMITED", "date_of_creation": "2019-03-14", **changes})


def test_matching_name_and_date_is_present_and_says_so():
    result = run(full_certificate(), returns(register()))
    assert result.status is Status.PRESENT
    assert result.finding.endswith("Name and incorporation date match the certificate")


def test_only_name_compared_when_register_has_no_date():
    reply = register()
    del reply["date_of_creation"]
    assert run(full_certificate(), returns(reply)).finding.endswith("Name matches the certificate")


def test_different_name_is_unclear():
    result = run(full_certificate(), returns(register(company_name="BOCIOC M LIMITED")))
    assert result.status is Status.UNCLEAR
    assert result.finding == (
        "Name on certificate 'EXAMPLE PAYMENTS LTD' does not match Companies House 'BOCIOC M LIMITED'"
    )


def test_different_incorporation_date_is_unclear():
    result = run(full_certificate(), returns(register(date_of_creation="2020-01-02")))
    assert result.status is Status.UNCLEAR
    assert result.finding == (
        "Incorporation date on certificate 14 Mar 2019 does not match Companies House 2 Jan 2020"
    )


def test_red_flag_and_mismatch_are_both_listed_and_need_human_review():
    reply = register(status="dissolved", company_name="BOCIOC M LIMITED")
    result = run(full_certificate(), returns(reply))
    assert result.status is Status.NEEDS_HUMAN_REVIEW
    assert result.finding == (
        "Companies House status: dissolved; "
        "name on certificate 'EXAMPLE PAYMENTS LTD' does not match Companies House 'BOCIOC M LIMITED'"
    )


def test_nothing_compared_when_certificate_lacks_name_and_date():
    result = run(certificate(), returns(register(company_name="SOMEONE ELSE LTD")))
    assert result.status is Status.PRESENT
    assert "certificate" not in result.finding


def test_unreadable_certificate_date_is_not_compared():
    result = run(full_certificate(incorporated="14th of Marhc"), returns(register(date_of_creation="2020-01-02")))
    assert result.status is Status.PRESENT
    assert result.finding.endswith("Name matches the certificate")
