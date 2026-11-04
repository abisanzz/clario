from dataclasses import replace
from datetime import date

import pytest

from services.documents import CertificateOfIncorporation, Fact, OnboardingQuestionnaire, ProofOfAddress
from services.validator import Status, _months_before, _same_company_name, check_1_2

TODAY = date(2026, 10, 5)
PROOF_P1 = "Proof of address p.1"
QUESTIONNAIRE = "Onboarding questionnaire q.4"
ADDRESS = "1 Example Street, London EC1A 1AA"

CERTIFICATE = CertificateOfIncorporation(company_name=Fact("EXAMPLE PAYMENTS LTD", "Certificate of incorporation p.1"))


def proof(**changes):
    """A complete, valid made-up proof of address; pass changes to break one part of it."""
    good = ProofOfAddress(
        company_name=Fact("Example Payments Limited", PROOF_P1),
        registered_office=Fact(ADDRESS, PROOF_P1),
        document_date=Fact(date(2026, 9, 2), PROOF_P1),
    )
    return replace(good, **changes)


def questionnaire(trades_from_registered_office=True, principal=None):
    return OnboardingQuestionnaire(
        trades_from_registered_office=Fact(trades_from_registered_office, QUESTIONNAIRE),
        principal_place_of_business=Fact(principal, QUESTIONNAIRE if principal else ""),
    )


def run(proof_of_address=None, answers=None, certificate=CERTIFICATE):
    return check_1_2(proof_of_address, answers, certificate, today=TODAY)


# --- Present ---

def test_trading_from_registered_office_is_present():
    result = run(proof(), questionnaire(True))
    assert result.check_id == "1.2"
    assert result.status is Status.PRESENT
    assert result.finding == f"Registered office: {ADDRESS}. Principal place of business: same as registered office"
    assert result.source_reference == f"{QUESTIONNAIRE}; {PROOF_P1}"


def test_trading_elsewhere_with_address_is_present():
    result = run(proof(), questionnaire(False, "Unit 4, Manchester M1 1AA"))
    assert result.status is Status.PRESENT
    assert result.finding.endswith("Principal place of business: Unit 4, Manchester M1 1AA")


# --- Missing ---

def test_no_proof_of_address_is_missing():
    result = run(None, questionnaire(True))
    assert result.status is Status.MISSING
    assert result.finding == ("No proof of registered address provided, and no registered office found in the "
                              "documents")


@pytest.mark.parametrize("empty", [None, "", "  "])
def test_no_registered_office_is_missing(empty):
    result = run(proof(registered_office=Fact(empty)), questionnaire(True))
    assert result.status is Status.MISSING
    assert result.finding == "Registered office address not found on proof of address"


def test_missing_wins_but_unclear_problems_are_also_reported():
    result = run(proof(registered_office=Fact(), document_date=Fact()), questionnaire(True))
    assert result.status is Status.MISSING
    assert result.finding == (
        "Registered office address not found on proof of address. "
        "Also: proof of address has no date, so its age cannot be confirmed"
    )


# --- Principal place of business ---

def test_trading_elsewhere_without_address_is_unclear():
    result = run(proof(), questionnaire(False))
    assert result.status is Status.UNCLEAR
    assert result.finding == "Client operates away from the registered office but gave no principal place of business"


@pytest.mark.parametrize("answers", [None, questionnaire(None)])
def test_question_not_answered_is_unclear(answers):
    result = run(proof(), answers)
    assert result.status is Status.UNCLEAR
    assert result.finding == "Not stated whether the principal place of business differs from the registered office"


# --- Age of proof of address ---

def test_exactly_three_months_old_is_fine():
    assert run(proof(document_date=Fact(date(2026, 7, 5), PROOF_P1)), questionnaire(True)).status is Status.PRESENT


def test_older_than_three_months_is_unclear():
    result = run(proof(document_date=Fact(date(2026, 7, 4), PROOF_P1)), questionnaire(True))
    assert result.status is Status.UNCLEAR
    assert result.finding == "Proof of address is dated 4 Jul 2026, more than 3 months ago"


def test_future_dated_is_unclear():
    result = run(proof(document_date=Fact(date(2026, 12, 1), PROOF_P1)), questionnaire(True))
    assert result.status is Status.UNCLEAR
    assert result.finding == "Proof of address is dated in the future (1 Dec 2026)"


def test_undated_is_unclear():
    result = run(proof(document_date=Fact()), questionnaire(True))
    assert result.status is Status.UNCLEAR
    assert result.finding == "Proof of address has no date, so its age cannot be confirmed"


def test_unreadable_date_is_unclear():
    result = run(proof(document_date=Fact("Sept-ish", PROOF_P1)), questionnaire(True))
    assert result.status is Status.UNCLEAR
    assert result.finding == "Proof of address date 'Sept-ish' could not be read as a date"


@pytest.mark.parametrize("today, expected", [
    (date(2026, 10, 5), date(2026, 7, 5)),
    (date(2026, 5, 31), date(2026, 2, 28)),
    (date(2028, 5, 31), date(2028, 2, 29)),
    (date(2026, 1, 15), date(2025, 10, 15)),
])
def test_three_months_before_handles_month_ends_and_years(today, expected):
    assert _months_before(today, 3) == expected


# --- Company name ---

def test_different_company_name_is_unclear():
    result = run(proof(company_name=Fact("EXAMPLE PAY LTD", PROOF_P1)), questionnaire(True))
    assert result.status is Status.UNCLEAR
    assert result.finding == "Proof of address is for 'EXAMPLE PAY LTD', certificate says 'EXAMPLE PAYMENTS LTD'"


def test_no_company_name_on_proof_is_unclear():
    result = run(proof(company_name=Fact()), questionnaire(True))
    assert result.status is Status.UNCLEAR
    assert result.finding == "Company name not found on proof of address, so it cannot be matched to the client"


def test_name_not_compared_without_certificate():
    assert run(proof(), questionnaire(True), certificate=None).status is Status.PRESENT


@pytest.mark.parametrize("a, b", [
    ("EXAMPLE PAYMENTS LTD", "Example Payments Limited"),
    ("EXAMPLE PAYMENTS LTD.", "example  payments  ltd"),
    ("SMITH & JONES LTD", "Smith and Jones Limited"),
    ("BIG BANK PLC", "Big Bank Public Limited Company"),
])
def test_harmless_name_differences_still_match(a, b):
    assert _same_company_name(a, b)


@pytest.mark.parametrize("a, b", [
    ("EXAMPLE PAYMENTS LTD", "EXAMPLE PAY LTD"),
    ("EXAMPLE PAYMENTS LTD", "EXAMPLE PAYMENTS PLC"),
    ("EXAMPLE PAYMENTS LTD", "EXAMPLE PAYMENTS (UK) LTD"),
])
def test_real_name_differences_do_not_match(a, b):
    assert not _same_company_name(a, b)


def test_several_problems_are_all_listed():
    result = run(
        proof(company_name=Fact("OTHER CO LTD", PROOF_P1), document_date=Fact(date(2025, 1, 1), PROOF_P1)),
        questionnaire(False),
    )
    assert result.status is Status.UNCLEAR
    assert "dated 1 Jan 2025" in result.finding
    assert "'OTHER CO LTD'" in result.finding
    assert "gave no principal place of business" in result.finding


def test_an_office_only_in_the_documents_is_unclear_not_missing():
    quotes = ['01_Certificate.pdf p.1: "Registered office 20 Example Square, London, EC2A 4TEST"',
              '03_Confirmation_Statement.pdf p.1: "Registered office 20 Example Square, London, EC2A 4TEST"',
              '05_Chart.pdf p.1: "Two direct owners"']  # not about the address, so not counted
    result = check_1_2(None, None, office_quotes=quotes)
    assert result.status is Status.UNCLEAR
    assert result.finding.startswith("The registered office appears in 2 document(s) (01_Certificate.pdf, "
                                     "03_Confirmation_Statement.pdf), but no proof of registered address was provided")
    assert "not been checked against Companies House" in result.finding


def test_companies_house_can_confirm_the_registered_office():
    certificate = CertificateOfIncorporation(company_name=Fact("EXAMPLE LTD"), company_number=Fact("12345678"))
    record = {"registered_office_address": {"address_line_1": "1 High Street", "locality": "London",
                                            "postal_code": "EC1A 1AA"}}
    trades_there = check_1_2(None, questionnaire(True), certificate, lookup=lambda number: record)
    assert trades_there.status is Status.PRESENT and "confirmed on Companies House" in trades_there.finding
    unknown = check_1_2(None, None, certificate, lookup=lambda number: record)
    assert unknown.status is Status.UNCLEAR and "principal place of business" in unknown.finding
