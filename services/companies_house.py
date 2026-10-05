"""Fetch company records from the Companies House API."""

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

API_URL = "https://api.company-information.service.gov.uk/company/{number}"
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
TIMEOUT_SECONDS = 15


class CompanyNotFound(Exception):
    """Companies House has no company with this number."""


class LookupFailed(Exception):
    """The lookup could not be completed; the message says why (never includes the key)."""


def get_company(company_number: str) -> dict:
    """Return the Companies House record for a company number."""
    load_dotenv(ENV_PATH)
    key = os.getenv("COMPANIES_HOUSE_API_KEY", "").strip()
    if not key:
        raise LookupFailed("no Companies House API key set in .env")

    request = urllib.request.Request(
        API_URL.format(number=urllib.parse.quote(company_number)),
        headers={"Authorization": "Basic " + base64.b64encode(f"{key}:".encode()).decode()},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise CompanyNotFound(company_number) from error
        if error.code == 401:
            raise LookupFailed("API key was rejected") from error
        if error.code == 429:
            raise LookupFailed("too many requests; try again in a few minutes") from error
        raise LookupFailed(f"Companies House replied with error {error.code}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise LookupFailed("no response from Companies House") from error
    except json.JSONDecodeError as error:
        raise LookupFailed("Companies House sent a reply that could not be read") from error
