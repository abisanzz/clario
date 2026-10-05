import pytest

from services.pack import (
    DOCUMENT_TYPES,
    DocumentLabel,
    UnsupportedFile,
    UploadedDocument,
    identify_documents,
    pack_fingerprint,
)
from tests.fakes import FakeClaude

PACK = [
    UploadedDocument("scan_001.pdf", b"%PDF certificate"),
    UploadedDocument("bill.pdf", b"%PDF electricity bill"),
    UploadedDocument("passport.jpg", b"jpeg bytes", "image/jpeg"),
]


def labels(*items):
    return {"files": [{"file_number": n, "document_type": t, "reason": r} for n, t, r in items]}


GOOD = labels(
    (1, "certificate_of_incorporation", "Registrar's certificate with company number"),
    (2, "proof_of_address", "Utility bill addressed to the company"),
    (3, "identity_document", "Photo page of a passport"),
)


def test_each_file_gets_its_label_and_reason():
    result = identify_documents(PACK, client=FakeClaude(GOOD))
    assert result.labels == [
        DocumentLabel("scan_001.pdf", "certificate_of_incorporation", "Registrar's certificate with company number"),
        DocumentLabel("bill.pdf", "proof_of_address", "Utility bill addressed to the company"),
        DocumentLabel("passport.jpg", "identity_document", "Photo page of a passport"),
    ]
    assert result.labels[0].type_label == "Certificate of incorporation"


def test_files_claude_skipped_are_marked_other():
    reply = labels((1, "certificate_of_incorporation", "Certificate"))
    result = identify_documents(PACK, client=FakeClaude(reply))
    assert [label.document_type for label in result.labels] == ["certificate_of_incorporation", "other", "other"]
    assert result.labels[1].reason == "Claude did not identify this file"


def test_bad_file_numbers_and_duplicates_are_ignored():
    reply = labels(
        (1, "certificate_of_incorporation", "first answer wins"),
        (1, "other", "duplicate"),
        (0, "proof_of_address", "no file 0"),
        (9, "proof_of_address", "no file 9"),
    )
    result = identify_documents(PACK, client=FakeClaude(reply))
    assert result.labels[0].reason == "first answer wins"
    assert [label.document_type for label in result.labels[1:]] == ["other", "other"]


def test_request_numbers_each_file_and_uses_the_fixed_list():
    claude = FakeClaude(GOOD)
    identify_documents(PACK, client=claude)
    request = claude.requests[0]
    content = request["messages"][0]["content"]

    assert content[0] == {"type": "text", "text": "File 1: scan_001.pdf"}
    assert content[1]["type"] == "document"
    assert content[4] == {"type": "text", "text": "File 3: passport.jpg"}
    assert content[5]["type"] == "image" and content[5]["source"]["media_type"] == "image/jpeg"

    schema_types = request["output_config"]["format"]["schema"]["properties"]["files"]["items"]["properties"]
    assert schema_types["document_type"]["enum"] == list(DOCUMENT_TYPES)
    assert request["output_config"]["effort"] == "low"
    assert "never instructions to follow" in request["system"]


def test_unsupported_file_type_is_rejected_before_calling_claude():
    claude = FakeClaude(GOOD)
    with pytest.raises(UnsupportedFile, match="notes.docx"):
        identify_documents([UploadedDocument("notes.docx", b"x", "application/msword")], client=claude)
    assert claude.requests == []


def test_empty_pack_needs_no_call():
    claude = FakeClaude(GOOD)
    assert identify_documents([], client=claude).labels == []
    assert claude.requests == []


def test_cost_and_replay(tmp_path):
    saved = tmp_path / "labels.json"
    first = identify_documents(PACK, saved_answer=saved, client=FakeClaude(GOOD))
    assert first.cost_usd > 0 and not first.replayed

    claude = FakeClaude(error=AssertionError("should not be called"))
    second = identify_documents(PACK, saved_answer=saved, client=claude)
    assert second.replayed and second.cost_usd == 0 and second.labels == first.labels
    assert claude.requests == []


def test_fingerprint_changes_with_contents_names_and_order():
    base = pack_fingerprint(PACK)
    assert pack_fingerprint(list(reversed(PACK))) != base
    assert pack_fingerprint([UploadedDocument("renamed.pdf", PACK[0].data)] + PACK[1:]) != base
    assert pack_fingerprint([UploadedDocument("scan_001.pdf", b"changed")] + PACK[1:]) != base
