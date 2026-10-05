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
