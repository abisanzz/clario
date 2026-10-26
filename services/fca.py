"""Fetch firm records from the FCA Financial Services Register API."""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

API_BASE = "https://register.fca.org.uk/services/V0.1"
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
TIMEOUT_SECONDS = 20
# The register's security service blocks requests that do not name the program asking
USER_AGENT = "Clario-KYC/0.1 (portfolio project)"
MAX_PAGES = 5  # permissions come in pages of 20; no firm needs more than this
MAX_INDIVIDUALS_LISTED = 20


class FirmNotFound(Exception):
    """The FCA register has no firm with this reference number."""


class FcaLookupFailed(Exception):
    """The lookup could not be completed; the message says why (never includes the key)."""


def _get(url: str) -> dict:
    """Fetch one FCA register API address and return the JSON reply."""
    load_dotenv(ENV_PATH)
    email, key = os.getenv("FCA_API_EMAIL", "").strip(), os.getenv("FCA_API_KEY", "").strip()
    if not email or not key:
        raise FcaLookupFailed("no FCA API email and key set in .env")

    request = urllib.request.Request(url, headers={
        "X-Auth-Email": email, "X-Auth-Key": key, "Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise FcaLookupFailed("the FCA register refused the request; check the email and key in .env") from error
        if error.code == 429:
            raise FcaLookupFailed("too many requests; try again in a minute") from error
        raise FcaLookupFailed(f"the FCA register replied with error {error.code}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise FcaLookupFailed("no response from the FCA register") from error
    except json.JSONDecodeError as error:
        raise FcaLookupFailed("the FCA register sent a reply that could not be read") from error


def _firm_path(frn: str, part: str = "") -> str:
    return f"{API_BASE}/Firm/{urllib.parse.quote(frn)}" + (f"/{part}" if part else "")


def get_firm(frn: str) -> dict:
    """The firm's main register entry: name, status, Companies House number and more."""
    data = _get(_firm_path(frn)).get("Data")
    if not data:
        raise FirmNotFound(frn)
    return data[0]


def _optional_list(url: str) -> list:
    """Items from a part of the register that may be empty (the register then sends no data)."""
    data = _get(url).get("Data")
    return data if isinstance(data, list) else []


def get_permissions(frn: str) -> dict[str, list]:
    """Each permission's name and its details, reading every page."""
    permissions, url = {}, _firm_path(frn, "Permissions")
    for _ in range(MAX_PAGES):
        reply = _get(url)
        permissions.update(reply.get("Data") or {})
        url = (reply.get("ResultInfo") or {}).get("Next")
        if not url:
            break
    return permissions


def get_requirements(frn: str) -> list[dict]:
    return _optional_list(_firm_path(frn, "Requirements"))


def get_individuals(frn: str) -> tuple[list[dict], int]:
    """The first page of people linked to the firm, and how many there are in total."""
    reply = _get(_firm_path(frn, "Individuals"))
    total = (reply.get("ResultInfo") or {}).get("total_count") or 0
    items = reply.get("Data") if isinstance(reply.get("Data"), list) else []
    return items, int(total)


def get_disciplinary_history(frn: str) -> list[dict]:
    return _optional_list(_firm_path(frn, "DisciplinaryHistory"))


def parse_frn(text: str) -> str | None:
    """A firm reference number (6 or 7 digits) from what the user typed, or None if there isn't one."""
    candidate = re.sub(r"[\s-]", "", (text or "").strip())
    candidate = re.sub(r"^FRN:?", "", candidate, flags=re.IGNORECASE)
    return candidate if re.fullmatch(r"\d{6,7}", candidate) else None


# Fields from the main entry worth showing, in this order (empty ones are left out)
FIRM_FIELDS = [
    "Organisation Name", "FRN", "Status", "Status Effective Date", "Sub-Status", "Business Type",
    "Companies House Number", "Client Money Permission", "PSD / EMD Status", "PSD / EMD Effective Date",
    "PSD Agent Status", "E-Money Agent Status", "MLRs Status", "MLRs Status Effective Date",
]


def _permission_line(name: str, details: list) -> str:
    parts = []
    for detail in details or []:
        for label, values in (detail or {}).items():
            if label != "Limitation Not Found" and values:
                parts.append(f"{label}: {', '.join(str(v) for v in values)}")
    return f"- {name}" + (f" ({'; '.join(parts)})" if parts else "")


def fca_summary(frn: str) -> str:
    """A plain-text summary of the firm's FCA register entry, for Claude to read alongside the documents."""
    firm = get_firm(frn)
    lines = [f"FCA Financial Services Register entry for firm reference number {frn} (fetched from the official API)."]
    lines += [f"{field}: {firm[field]}" for field in FIRM_FIELDS if firm.get(field)]

    permissions = get_permissions(frn)
    lines.append("Permissions:")
    lines += [_permission_line(name, details) for name, details in permissions.items()] or ["- none listed"]

    lines.append("Requirements and restrictions:")
    for requirement in get_requirements(frn) or [None]:
        lines.append("- " + ("; ".join(f"{k}: {v}" for k, v in requirement.items() if v) if requirement else "none listed"))

    lines.append("Disciplinary history:")
    for action in get_disciplinary_history(frn) or [None]:
        lines.append("- " + (
            f"{action.get('TypeofAction', 'Action')} from {action.get('ActionEffectiveFrom', 'date not shown')}: "
            f"{action.get('TypeofDescription', '')}" if action else "none listed"))

    individuals, total = get_individuals(frn)
    shown = individuals[:MAX_INDIVIDUALS_LISTED]
    lines.append(f"Individuals linked to the firm: {total} in total"
                 + (f"; the first {len(shown)}:" if total > len(shown) else ":"))
    lines += [f"- {p.get('Name')} ({p.get('Status', 'status not shown')})" for p in shown] or ["- none listed"]
    return "\n".join(lines)
