"""Fetch company records from the Companies House API."""

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

API_BASE = "https://api.company-information.service.gov.uk"
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
TIMEOUT_SECONDS = 15


class CompanyNotFound(Exception):
    """Companies House has no company with this number."""


class LookupFailed(Exception):
    """The lookup could not be completed; the message says why (never includes the key)."""


def _get(path: str, not_found: str) -> dict:
    """Fetch one Companies House API path and return the JSON reply."""
    load_dotenv(ENV_PATH)
    key = os.getenv("COMPANIES_HOUSE_API_KEY", "").strip()
    if not key:
        raise LookupFailed("no Companies House API key set in .env")

    request = urllib.request.Request(
        API_BASE + path,
        headers={"Authorization": "Basic " + base64.b64encode(f"{key}:".encode()).decode()},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise CompanyNotFound(not_found) from error
        if error.code == 401:
            raise LookupFailed("API key was rejected") from error
        if error.code == 429:
            raise LookupFailed("too many requests; try again in a few minutes") from error
        raise LookupFailed(f"Companies House replied with error {error.code}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise LookupFailed("no response from Companies House") from error
    except json.JSONDecodeError as error:
        raise LookupFailed("Companies House sent a reply that could not be read") from error


def get_company(company_number: str) -> dict:
    """Return the Companies House record for a company number."""
    return _get(f"/company/{urllib.parse.quote(company_number)}", company_number)


def get_officers(company_number: str) -> list[dict]:
    """Return the company's officers (directors and secretaries), current and past."""
    path = f"/company/{urllib.parse.quote(company_number)}/officers?items_per_page=100"
    return _get(path, company_number).get("items") or []


def get_persons_with_significant_control(company_number: str) -> list[dict]:
    """Return the company's PSC register entries (owners and controllers)."""
    path = f"/company/{urllib.parse.quote(company_number)}/persons-with-significant-control?items_per_page=100"
    return _get(path, company_number).get("items") or []


def parse_company_number(link_or_number: str) -> str | None:
    """Pull a company number out of a Companies House link, or tidy a bare number. None if there isn't one."""
    text = (link_or_number or "").strip()
    match = re.search(r"/company/([A-Za-z0-9]{8})(?:/|$|\?|#)", text)
    candidate = match.group(1) if match else re.sub(r"\s", "", text)
    candidate = candidate.upper()
    return candidate if re.fullmatch(r"\d{8}|[A-Z]{2}\d{6}", candidate) else None


def _readable(value: str) -> str:
    return str(value).replace("-", " ")


def companies_house_summary(company_number: str) -> str:
    """A plain-text summary of the company's public record, for Claude to read alongside the documents."""
    profile = get_company(company_number)
    lines = [
        f"Companies House public record for company number {company_number} (fetched from the official API).",
        f"Company name: {profile.get('company_name', 'not shown')}",
        f"Status: {profile.get('company_status', 'not shown')}",
        f"Company type: {_readable(profile.get('type', 'not shown'))}",
        f"Date of creation: {profile.get('date_of_creation', 'not shown')}",
    ]
    office = profile.get("registered_office_address") or {}
    if office:
        parts = ("address_line_1", "address_line_2", "locality", "region", "postal_code", "country")
        lines.append("Registered office: " + ", ".join(office[p] for p in parts if office.get(p)))
    accounts = profile.get("accounts") or {}
    confirmation = profile.get("confirmation_statement") or {}
    lines.append(f"Accounts next due: {accounts.get('next_due', 'not shown')} (overdue: {bool(accounts.get('overdue'))})")
    lines.append(
        f"Confirmation statement next due: {confirmation.get('next_due', 'not shown')} "
        f"(overdue: {bool(confirmation.get('overdue'))})"
    )

    for title, fetch, describe in (
        ("Officers", get_officers, lambda o: (
            f"{o.get('name')} - {_readable(o.get('officer_role', ''))}, appointed {o.get('appointed_on', 'not shown')}"
            + (f", resigned {o['resigned_on']}" if o.get("resigned_on") else "")
        )),
        ("Persons with significant control", get_persons_with_significant_control, lambda p: (
            f"{p.get('name')} - " + "; ".join(_readable(n) for n in p.get("natures_of_control", []))
            + f", notified {p.get('notified_on', 'not shown')}"
            + (f", ceased {p['ceased_on']}" if p.get("ceased_on") else "")
        )),
    ):
        try:
            items = fetch(company_number)
        except CompanyNotFound:
            items = []
        lines.append(f"{title}:")
        lines.extend(f"- {describe(item)}" for item in items) if items else lines.append("- none listed")
    return "\n".join(lines)
