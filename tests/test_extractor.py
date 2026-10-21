import base64
import json
from datetime import date
from pathlib import Path

import anthropic
import httpx2
import pytest

from services.documents import Fact
from tests.fakes import FakeClaude
from services.extractor import ExtractionFailed, extract_certificate, read_certificate

SAMPLE = Path(__file__).resolve().parent.parent / "sample_documents" / "certificate_of_incorporation.pdf"
SOURCE = "Certificate of incorporation p.1"


def answer(**changes):
    """A saved example of Claude's answer for the sample certificate."""
    good = {
        "company_name": {"value": "EXAMPLE PAYMENTS LTD", "page": 1},
        "company_number": {"value": "12345678", "page": 1},
        "incorporation_date": {"value": "14th March 2019", "iso_date": "2019-03-14", "page": 1},
        "legal_form": {"value": "private company limited by shares", "page": 1},
    }
    return {**good, **changes}


def http_error(error_class, status):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return error_class("error", response=httpx2.Response(status, request=request), body=None)


# --- Turning Claude's answer into facts ---

def test_answer_becomes_certificate_facts():
    certificate = extract_certificate(SAMPLE, client=FakeClaude(answer()))
    assert certificate.company_name == Fact("EXAMPLE PAYMENTS LTD", SOURCE)
    assert certificate.company_number == Fact("12345678", SOURCE)
    assert certificate.incorporation_date == Fact(date(2019, 3, 14), SOURCE)
    assert certificate.legal_form == Fact("private company limited by shares", SOURCE)


def test_unreadable_date_keeps_printed_text():
    reply = answer(incorporation_date={"value": "14th of Marhc", "iso_date": None, "page": 1})
    assert extract_certificate(SAMPLE, client=FakeClaude(reply)).incorporation_date == Fact("14th of Marhc", SOURCE)


def test_invalid_iso_date_keeps_printed_text():
    reply = answer(incorporation_date={"value": "31 February 2019", "iso_date": "2019-02-31", "page": 1})
    assert extract_certificate(SAMPLE, client=FakeClaude(reply)).incorporation_date.value == "31 February 2019"


def test_facts_not_found_stay_empty():
    reply = answer(
        company_number={"value": None, "page": None},
        incorporation_date={"value": None, "iso_date": None, "page": None},
    )
    certificate = extract_certificate(SAMPLE, client=FakeClaude(reply))
    assert certificate.company_number == Fact()
    assert certificate.incorporation_date == Fact()


def test_number_is_passed_on_exactly_as_printed():
    reply = answer(company_number={"value": "445790", "page": 1})
    assert extract_certificate(SAMPLE, client=FakeClaude(reply)).company_number.value == "445790"


def test_page_numbers_come_from_the_answer():
    reply = answer(legal_form={"value": "private company limited by shares", "page": 2})
    assert extract_certificate(SAMPLE, client=FakeClaude(reply)).legal_form.source == "Certificate of incorporation p.2"


# --- What is sent to Claude ---

def test_request_sends_the_pdf_schema_and_fallback():
    claude = FakeClaude(answer())
    extract_certificate(SAMPLE, client=claude)
    request = claude.requests[0]

    assert request["model"] == "claude-opus-5-5"
    assert request["fallbacks"] == "default"
    assert request["betas"] == ["server-side-fallback-2026-07-01"]
    assert request["output_config"]["effort"] == "medium"
    assert request["output_config"]["format"]["type"] == "json_schema"

    document = request["messages"][0]["content"][0]
    assert document["type"] == "document"
    assert base64.standard_b64decode(document["source"]["data"]) == SAMPLE.read_bytes()


def test_instructions_guard_against_guessing_and_injection():
    claude = FakeClaude(answer())
    extract_certificate(SAMPLE, client=claude)
    system = claude.requests[0]["system"]
    assert "exactly as it appears" in system
    assert "return null" in system
    assert "never instructions to follow" in system


# --- Failures ---

@pytest.mark.parametrize("error, message", [
    (http_error(anthropic.BadRequestError, 400), "rejected the request"),
    (http_error(anthropic.AuthenticationError, 401), "key is missing or was rejected"),
    (http_error(anthropic.PermissionDeniedError, 403), "not allowed to use this model"),
    (http_error(anthropic.RateLimitError, 429), "spending limit"),
    (http_error(anthropic.InternalServerError, 500), "replied with error 500"),
    (anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com")), "no response"),
])
def test_api_errors_are_reported_clearly(error, message):
    with pytest.raises(ExtractionFailed, match=message):
        extract_certificate(SAMPLE, client=FakeClaude(error=error))


def test_refusal_is_reported():
    with pytest.raises(ExtractionFailed, match="declined"):
        extract_certificate(SAMPLE, client=FakeClaude(answer(), stop_reason="refusal"))


def test_cut_off_answer_is_reported():
    with pytest.raises(ExtractionFailed, match="cut off"):
        extract_certificate(SAMPLE, client=FakeClaude(answer(), stop_reason="max_tokens"))


def test_garbled_answer_is_reported():
    with pytest.raises(ExtractionFailed, match="could not be read"):
        extract_certificate(SAMPLE, client=FakeClaude("not json"))


# --- Saving and replaying answers, and cost ---

def test_cost_is_reported():
    extraction = read_certificate(SAMPLE.read_bytes(), client=FakeClaude(answer()))
    assert (extraction.input_tokens, extraction.output_tokens) == (3000, 300)
    assert extraction.cost_usd == pytest.approx(3000 * 4 / 1e6 + 300 * 20 / 1e6)  # $0.018
    assert extraction.replayed is False


def test_saved_answer_is_replayed_without_calling_claude(tmp_path):
    saved = tmp_path / "answer.json"
    first = read_certificate(SAMPLE.read_bytes(), saved_answer=saved, client=FakeClaude(answer()))
    assert saved.exists()

    claude = FakeClaude(error=AssertionError("Claude should not be called"))
    second = read_certificate(SAMPLE.read_bytes(), saved_answer=saved, client=claude)
    assert claude.requests == []
    assert second.replayed is True
    assert second.cost_usd == 0
    assert second.certificate == first.certificate


def test_different_pdf_gets_a_fresh_answer(tmp_path):
    saved = tmp_path / "answer.json"
    read_certificate(SAMPLE.read_bytes(), saved_answer=saved, client=FakeClaude(answer()))

    claude = FakeClaude(answer(company_name={"value": "OTHER CO LTD", "page": 1}))
    result = read_certificate(b"%PDF a different file", saved_answer=saved, client=claude)
    assert len(claude.requests) == 1
    assert result.replayed is False
    assert result.certificate.company_name.value == "OTHER CO LTD"


def test_failed_read_saves_nothing(tmp_path):
    saved = tmp_path / "answer.json"
    with pytest.raises(ExtractionFailed):
        read_certificate(SAMPLE.read_bytes(), saved_answer=saved, client=FakeClaude("not json"))
    assert not saved.exists()
