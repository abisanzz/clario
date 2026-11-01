from services.countries import COUNTRIES, UNITED_KINGDOM, is_uk


def test_only_uk_companies_are_checked_on_the_uk_registers():
    assert is_uk(UNITED_KINGDOM) and is_uk("")  # reviews saved before the country was asked for
    assert not is_uk("Ireland") and not is_uk("Jersey")
    assert COUNTRIES[0] == UNITED_KINGDOM and len(set(COUNTRIES)) == len(COUNTRIES)
