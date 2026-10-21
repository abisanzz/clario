import io
import urllib.error

import pytest

from services import companies_house
from services.companies_house import CompanyNotFound, LookupFailed, get_company

FAKE_KEY = "test-key-not-real-1234"


@pytest.fixture
def key(monkeypatch, tmp_path):
    """Use a made-up key and an empty .env location, so tests never touch the real key."""
    monkeypatch.setattr(companies_house, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setenv("COMPANIES_HOUSE_API_KEY", FAKE_KEY)


def fake_web(monkeypatch, reply=None, error=None):
    """Replace the real web call with a fake that returns `reply` or raises `error`."""
    requests = []

    def urlopen(request, timeout):
        requests.append(request)
        if error:
            raise error
        return io.BytesIO(reply)

    monkeypatch.setattr(companies_house.urllib.request, "urlopen", urlopen)
    return requests


def http_error(code):
    return urllib.error.HTTPError("https://example", code, "error", {}, None)


def test_returns_the_record(key, monkeypatch):
    requests = fake_web(monkeypatch, reply=b'{"company_status": "active"}')
    assert get_company("12345678") == {"company_status": "active"}
    assert requests[0].full_url == "https://api.company-information.service.gov.uk/company/12345678"


def test_no_key_fails_without_going_online(monkeypatch, tmp_path):
    monkeypatch.setattr(companies_house, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setenv("COMPANIES_HOUSE_API_KEY", "")
    requests = fake_web(monkeypatch, reply=b"{}")
    with pytest.raises(LookupFailed, match="no Companies House API key set in .env"):
        get_company("12345678")
    assert requests == []


def test_unknown_company(key, monkeypatch):
    fake_web(monkeypatch, error=http_error(404))
    with pytest.raises(CompanyNotFound):
        get_company("12345678")


@pytest.mark.parametrize("error, message", [
    (http_error(401), "API key was rejected"),
    (http_error(429), "too many requests"),
    (http_error(500), "replied with error 500"),
    (urllib.error.URLError("no internet"), "no response from Companies House"),
    (TimeoutError(), "no response from Companies House"),
])
def test_failures_are_reported_clearly(key, monkeypatch, error, message):
    fake_web(monkeypatch, error=error)
    with pytest.raises(LookupFailed, match=message):
        get_company("12345678")


def test_unreadable_reply(key, monkeypatch):
    fake_web(monkeypatch, reply=b"<html>not json</html>")
    with pytest.raises(LookupFailed, match="could not be read"):
        get_company("12345678")


@pytest.mark.parametrize("error", [http_error(401), http_error(500), urllib.error.URLError("x")])
def test_key_never_appears_in_error_messages(key, monkeypatch, error):
    fake_web(monkeypatch, error=error)
    with pytest.raises(LookupFailed) as caught:
        get_company("12345678")
    assert FAKE_KEY not in str(caught.value)


# --- Links, officers, PSC and the summary ---

from services.companies_house import (  # noqa: E402
    companies_house_summary,
    nature_of_business,
    parse_company_number,
    sic_description,
)


@pytest.mark.parametrize("text, expected", [
    ("12345678", "12345678"),
    (" sc 123456 ", "SC123456"),
    ("https://find-and-update.company-information.service.gov.uk/company/00445790", "00445790"),
    ("https://find-and-update.company-information.service.gov.uk/company/00445790/officers", "00445790"),
    ("find-and-update.company-information.service.gov.uk/company/sc123456?x=1", "SC123456"),
    ("not a number", None),
    ("1234567", None),
    ("", None),
])
def test_parse_company_number(text, expected):
    assert parse_company_number(text) == expected


def fake_register(monkeypatch, replies):
    """Replace the web call: return a reply chosen by which address was asked for."""
    asked = []

    def urlopen(request, timeout):
        asked.append(request.full_url)
        for fragment, reply in replies.items():
            if fragment in request.full_url:
                if isinstance(reply, Exception):
                    raise reply
                return io.BytesIO(reply)
        raise AssertionError(f"unexpected address {request.full_url}")

    monkeypatch.setattr(companies_house.urllib.request, "urlopen", urlopen)
    return asked


PROFILE = (b'{"company_name": "EXAMPLE PAYMENTS LTD", "company_status": "active", "type": "ltd",'
           b' "date_of_creation": "2019-03-14", "registered_office_address": {"address_line_1": "1 Example Street",'
           b' "locality": "London", "postal_code": "EX1 1AA"}, "accounts": {"next_due": "2027-06-30", "overdue": false},'
           b' "confirmation_statement": {"next_due": "2027-03-14", "overdue": false},'
           b' "sic_codes": ["64999", "62012"]}')
OFFICERS = (b'{"items": [{"name": "SAMPLE, Alex", "officer_role": "director", "appointed_on": "2019-03-14"},'
            b' {"name": "OLD, Pat", "officer_role": "director", "appointed_on": "2019-03-14", "resigned_on": "2020-01-01"}]}')
PSC = (b'{"items": [{"name": "Alex Sample", "notified_on": "2019-03-14",'
       b' "natures_of_control": ["ownership-of-shares-50-to-75-percent", "voting-rights-50-to-75-percent"]}]}')


def test_summary_lists_profile_officers_and_psc(key, monkeypatch):
    asked = fake_register(monkeypatch, {"/officers": OFFICERS, "/persons-with": PSC, "/company/12345678": PROFILE})
    summary = companies_house_summary("12345678")
    assert "Company name: EXAMPLE PAYMENTS LTD" in summary
    assert "Registered office: 1 Example Street, London, EX1 1AA" in summary
    assert ("Nature of business (SIC codes): 64999 Financial intermediation not elsewhere classified; "
            "62012 Business and domestic software development") in summary
    assert "- SAMPLE, Alex - director, appointed 2019-03-14" in summary
    assert "- OLD, Pat - director, appointed 2019-03-14, resigned 2020-01-01" in summary
    assert "- Alex Sample - ownership of shares 50 to 75 percent; voting rights 50 to 75 percent" in summary
    assert len(asked) == 3


def test_summary_handles_missing_officer_and_psc_lists(key, monkeypatch):
    fake_register(monkeypatch, {"/officers": http_error(404), "/persons-with": http_error(404),
                                "/company/12345678": PROFILE})
    summary = companies_house_summary("12345678")
    assert summary.count("- none listed") == 2


def test_summary_for_unknown_company_raises(key, monkeypatch):
    fake_register(monkeypatch, {"/company/12345678": http_error(404)})
    with pytest.raises(CompanyNotFound):
        companies_house_summary("12345678")


def test_sic_description():
    assert sic_description("64999") == "Financial intermediation not elsewhere classified"
    assert sic_description(" 99999 ") == "Dormant Company"
    assert sic_description("00000") == "not in the official list"


def test_nature_of_business():
    assert nature_of_business({"sic_codes": ["66190"]}) == [("66190", "Activities auxiliary to financial intermediation not elsewhere classified")]
    assert nature_of_business({}) == []


def test_summary_says_when_no_sic_codes(key, monkeypatch):
    fake_register(monkeypatch, {"/company/12345678": b'{"company_name": "X"}'})
    assert "Nature of business (SIC codes): none listed" in companies_house_summary("12345678")
