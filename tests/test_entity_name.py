import pytest

from services.validator import entity_name_matches


@pytest.mark.parametrize("entered, registered", [
    ("EXAMPLE PAYMENTS LTD", "EXAMPLE PAYMENTS LTD"),
    ("Example Payments Limited", "EXAMPLE PAYMENTS LTD"),
    ("example payments ltd.", "EXAMPLE PAYMENTS LIMITED"),
    ("Smith & Jones PLC", "SMITH AND JONES PUBLIC LIMITED COMPANY"),
    ("  Example   Payments Ltd ", "EXAMPLE PAYMENTS LTD"),
])
def test_same_name_written_differently_matches(entered, registered):
    assert entity_name_matches(entered, registered)


@pytest.mark.parametrize("entered, registered", [
    ("Example Payments", "EXAMPLE PAYMENTS LTD"),  # legal form left off
    ("Example Payment Ltd", "EXAMPLE PAYMENTS LTD"),
    ("Example Payments Group Ltd", "EXAMPLE PAYMENTS LTD"),
    ("", "EXAMPLE PAYMENTS LTD"),
])
def test_different_names_do_not_match(entered, registered):
    assert not entity_name_matches(entered, registered)


from services.companies_house import CompanyNotFound, LookupFailed  # noqa: E402
from services.validator import entity_name_rule  # noqa: E402


def registered_as(name):
    return lambda number: {"company_name": name}


def test_rule_matches_the_registered_name():
    assert entity_name_rule("Monzo Bank Ltd", "09446231", registered_as("MONZO BANK LIMITED")) == (
        True, "Legal entity name entered matches Companies House (MONZO BANK LIMITED)")


def test_rule_reports_a_different_name():
    assert entity_name_rule("Monzo  Ltd", "09446231", registered_as("MONZO BANK LIMITED")) == (
        False, "Legal entity name entered (Monzo Ltd) does not match Companies House (MONZO BANK LIMITED)")


def test_rule_says_when_it_cannot_compare():
    def not_found(number):
        raise CompanyNotFound(number)

    def down(number):
        raise LookupFailed("no response from Companies House")

    assert entity_name_rule("X Ltd", "", registered_as("X LTD")) == (
        None, "Legal entity name entered (X Ltd) not compared: no company number")
    assert entity_name_rule("X Ltd", "99999901", not_found) == (
        None, "Legal entity name entered (X Ltd) not compared: company 99999901 is not on Companies House")
    assert entity_name_rule("X Ltd", "99999901", down)[0] is None
