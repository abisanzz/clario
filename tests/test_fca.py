import io
import json
import urllib.error

import pytest

from services import fca
from services.fca import FcaLookupFailed, FirmNotFound, fca_summary, get_firm, get_permissions, parse_frn

FAKE_EMAIL, FAKE_KEY = "tester@example.com", "test-key-not-real-1234"
BASE = "https://register.fca.org.uk/services/V0.1/Firm/123456"

FIRM = {"Data": [{"Organisation Name": "EXAMPLE PAYMENTS LTD", "FRN": "123456", "Status": "Authorised",
                  "Business Type": "Regulated", "Companies House Number": "99999901", "MLRs Status": "",
                  "PSD / EMD Status": "Authorised Payment Institution"}]}
PERMISSIONS_1 = {"ResultInfo": {"Next": BASE + "/Permissions?pgnp=2"}, "Data": {
    "Payment services": [{"Limitation Not Found": ["Valid limitation not present"]}],
    "Dealing in investments as principal": [{"Customer Type": ["Professional"]}, {"Investment Type": ["Share"]}]}}
PERMISSIONS_2 = {"ResultInfo": {}, "Data": {"Credit broking": [{"Customer Type": ["Retail"]}]}}
REQUIREMENTS = {"Data": [{"Requirement Reference": "OR-1", "Financial Promotions Requirement": "TRUE"}]}
DISCIPLINE = {"Data": [{"TypeofAction": "Fines", "ActionEffectiveFrom": "07/07/2025", "TypeofDescription": "Final notice"}]}
INDIVIDUALS = {"ResultInfo": {"total_count": "2"}, "Data": [{"Name": "Alex Sample", "Status": "Approved by regulator"},
                                                             {"Name": "Jamie Example", "Status": "Approved by regulator"}]}
NOT_FOUND = {"Message": "Firm not found", "Data": None}
EMPTY = {"Message": "Page Not found", "Data": None}


@pytest.fixture
def key(monkeypatch, tmp_path):
    """Use a made-up email and key and an empty .env location, so tests never touch the real key."""
    monkeypatch.setattr(fca, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setenv("FCA_API_EMAIL", FAKE_EMAIL)
    monkeypatch.setenv("FCA_API_KEY", FAKE_KEY)


def fake_register(monkeypatch, routes):
    """Answer each web address with the reply for the longest matching ending; record the requests."""
    requests = []

    def urlopen(request, timeout):
        requests.append(request)
        url = request.full_url
        match = max((ending for ending in routes if url.endswith(ending)), key=len, default=None)
        reply = routes[match] if match is not None else EMPTY
        if isinstance(reply, Exception):
            raise reply
        return io.BytesIO(json.dumps(reply).encode())

    monkeypatch.setattr(fca.urllib.request, "urlopen", urlopen)
    return requests


def http_error(code):
    return urllib.error.HTTPError("https://example", code, "error", {}, None)


def test_returns_the_firm_with_the_right_headers(key, monkeypatch):
    requests = fake_register(monkeypatch, {"/123456": FIRM})
    assert get_firm("123456")["Organisation Name"] == "EXAMPLE PAYMENTS LTD"
    request = requests[0]
    assert request.full_url == BASE
    assert request.get_header("X-auth-email") == FAKE_EMAIL and request.get_header("X-auth-key") == FAKE_KEY
    assert request.get_header("User-agent").startswith("Clario")


def test_unknown_firm(key, monkeypatch):
    fake_register(monkeypatch, {"/123456": NOT_FOUND})
    with pytest.raises(FirmNotFound):
        get_firm("123456")


def test_no_key_fails_without_going_online(monkeypatch, tmp_path):
    monkeypatch.setattr(fca, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setenv("FCA_API_EMAIL", "")
    monkeypatch.setenv("FCA_API_KEY", "")
    requests = fake_register(monkeypatch, {"/123456": FIRM})
    with pytest.raises(FcaLookupFailed, match="no FCA API email and key"):
        get_firm("123456")
    assert requests == []


@pytest.mark.parametrize("error, message", [
    (http_error(403), "refused the request"),
    (http_error(401), "refused the request"),
    (http_error(429), "too many requests"),
    (http_error(500), "error 500"),
    (urllib.error.URLError("down"), "no response"),
])
def test_failures_are_reported_clearly_without_the_key(key, monkeypatch, error, message):
    fake_register(monkeypatch, {"/123456": error})
    with pytest.raises(FcaLookupFailed, match=message) as raised:
        get_firm("123456")
    assert FAKE_KEY not in str(raised.value) and FAKE_EMAIL not in str(raised.value)


def test_every_page_of_permissions_is_read(key, monkeypatch):
    requests = fake_register(monkeypatch, {"/Permissions": PERMISSIONS_1, "/Permissions?pgnp=2": PERMISSIONS_2})
    assert list(get_permissions("123456")) == ["Payment services", "Dealing in investments as principal",
                                               "Credit broking"]
    assert len(requests) == 2


def test_summary_covers_details_permissions_restrictions_discipline_and_people(key, monkeypatch):
    fake_register(monkeypatch, {"/123456": FIRM, "/Permissions": PERMISSIONS_1, "/Permissions?pgnp=2": PERMISSIONS_2,
                                "/Requirements": REQUIREMENTS, "/DisciplinaryHistory": DISCIPLINE,
                                "/Individuals": INDIVIDUALS})
    summary = fca_summary("123456")
    assert "Organisation Name: EXAMPLE PAYMENTS LTD" in summary
    assert "Companies House Number: 99999901" in summary
    assert "MLRs Status" not in summary  # empty fields are left out
    assert "- Payment services" in summary
    assert "- Dealing in investments as principal (Customer Type: Professional; Investment Type: Share)" in summary
    assert "- Requirement Reference: OR-1; Financial Promotions Requirement: TRUE" in summary
    assert "- Fines from 07/07/2025: Final notice" in summary
    assert "Individuals linked to the firm: 2 in total:" in summary
    assert "- Alex Sample (Approved by regulator)" in summary


def test_summary_says_when_sections_are_empty(key, monkeypatch):
    fake_register(monkeypatch, {"/123456": FIRM})  # every other part of the register is empty
    summary = fca_summary("123456")
    assert summary.count("- none listed") == 4


@pytest.mark.parametrize("text, expected", [
    ("730427", "730427"),
    (" 730 427 ", "730427"),
    ("FRN: 1234567", "1234567"),
    ("frn730427", "730427"),
    ("12345", None),
    ("https://register.fca.org.uk/s/firm?id=001b000000NMfYQAA1", None),
    ("", None),
])
def test_parse_frn(text, expected):
    assert parse_frn(text) == expected
