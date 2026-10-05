"""Fetch the readable text of a company's website, for Claude to read alongside the documents."""

import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urlparse

TIMEOUT_SECONDS = 15
MAX_DOWNLOAD_BYTES = 2_000_000
MAX_TEXT_CHARACTERS = 20_000  # keeps a large page from running up the Claude bill
USER_AGENT = "Clario-KYC-check/1.0"


class WebsiteFetchFailed(Exception):
    """The website could not be read; the message says why."""


class _TextOnly(HTMLParser):
    """Collects visible text, skipping scripts, styles and other non-visible parts."""

    SKIP = {"script", "style", "noscript", "svg", "head", "template"}

    def __init__(self):
        super().__init__()
        self.parts, self._skipping = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skipping += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skipping:
            self._skipping -= 1

    def handle_data(self, data):
        if not self._skipping and data.strip():
            self.parts.append(" ".join(data.split()))


def website_text(url: str) -> str:
    """Return the readable text of one web page, headed by its address."""
    url = (url or "").strip()
    if "://" not in url:
        url = "https://" + url
    if urlparse(url).scheme not in ("http", "https") or not urlparse(url).netloc:
        raise WebsiteFetchFailed(f"'{url}' is not a web address")

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            html = response.read(MAX_DOWNLOAD_BYTES).decode(response.headers.get_content_charset() or "utf-8", "replace")
    except urllib.error.HTTPError as error:
        raise WebsiteFetchFailed(f"the website replied with error {error.code}") from error
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        raise WebsiteFetchFailed("the website could not be reached") from error

    parser = _TextOnly()
    parser.feed(html)
    text = "\n".join(parser.parts)
    if not text:
        raise WebsiteFetchFailed("the page has no readable text (it may need JavaScript to display)")
    if len(text) > MAX_TEXT_CHARACTERS:
        text = text[:MAX_TEXT_CHARACTERS] + "\n[... page text shortened ...]"
    return f"Text of the company website {url} (fetched on this computer).\n\n{text}"
