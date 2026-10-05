import io
import urllib.error

import pytest

from services import website
from services.website import WebsiteFetchFailed, website_text

PAGE = b"""<html><head><title>Example Payments</title><style>body{color:red}</style></head>
<body><script>var secret = 1;</script><h1>Example Payments</h1>
<p>We help   small businesses
take card payments.</p><noscript>Enable JS</noscript></body></html>"""


class FakeResponse(io.BytesIO):
    def __init__(self, body, charset="utf-8"):
        super().__init__(body)
        self.headers = type("Headers", (), {"get_content_charset": lambda self: charset})()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def fake_web(monkeypatch, body=None, error=None):
    asked = []

    def urlopen(request, timeout):
        asked.append(request.full_url)
        if error:
            raise error
        return FakeResponse(body)

    monkeypatch.setattr(website.urllib.request, "urlopen", urlopen)
    return asked


def test_keeps_visible_text_only(monkeypatch):
    fake_web(monkeypatch, PAGE)
    text = website_text("https://example.com")
    assert "Example Payments" in text
    assert "We help small businesses" in text
    assert "secret" not in text and "color:red" not in text and "Enable JS" not in text
    assert text.startswith("Text of the company website https://example.com")


def test_adds_https_when_missing(monkeypatch):
    asked = fake_web(monkeypatch, PAGE)
    website_text("example.com")
    assert asked == ["https://example.com"]


def test_long_pages_are_shortened(monkeypatch):
    fake_web(monkeypatch, b"<p>" + b"word " * 10_000 + b"</p>")
    text = website_text("https://example.com")
    assert text.endswith("[... page text shortened ...]")
    assert len(text) < website.MAX_TEXT_CHARACTERS + 200


@pytest.mark.parametrize("url", ["ftp://example.com", "file:///etc/passwd", "https://"])
def test_rejects_non_web_addresses(monkeypatch, url):
    asked = fake_web(monkeypatch, PAGE)
    with pytest.raises(WebsiteFetchFailed, match="not a web address"):
        website_text(url)
    assert asked == []


@pytest.mark.parametrize("error, message", [
    (urllib.error.HTTPError("https://example.com", 404, "Not found", {}, None), "error 404"),
    (urllib.error.URLError("no internet"), "could not be reached"),
    (TimeoutError(), "could not be reached"),
])
def test_failures_are_reported(monkeypatch, error, message):
    fake_web(monkeypatch, error=error)
    with pytest.raises(WebsiteFetchFailed, match=message):
        website_text("https://example.com")


def test_page_without_text_is_reported(monkeypatch):
    fake_web(monkeypatch, b"<html><body><script>render()</script></body></html>")
    with pytest.raises(WebsiteFetchFailed, match="no readable text"):
        website_text("https://example.com")
