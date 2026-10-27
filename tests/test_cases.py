import pytest

from services.cases import answer_paths, list_cases, load_case, new_case_id, save_case
from services.pack import UploadedDocument

DETAILS = {"source": "Upload documents", "entity_name": "EXAMPLE PAYMENTS LTD", "company_link": "99999901",
           "website": "", "fca_frn": "999999", "not_a_field": "ignored"}
CERT = UploadedDocument("cert.pdf", b"%PDF cert")
BILL = UploadedDocument("bill.pdf", b"%PDF bill")
PHOTO = UploadedDocument("passport.jpg", b"jpeg bytes", "image/jpeg")


def test_a_draft_comes_back_exactly(tmp_path):
    case_id = new_case_id()
    save_case(case_id, DETAILS, [CERT, PHOTO], folder=tmp_path)
    details, documents = load_case(case_id, folder=tmp_path)
    assert details == {k: DETAILS[k] for k in ("source", "entity_name", "company_link", "website", "fca_frn")}
    assert documents == [CERT, PHOTO]


def test_adding_and_removing_documents(tmp_path):
    case_id = new_case_id()
    save_case(case_id, DETAILS, [CERT, BILL], folder=tmp_path)
    save_case(case_id, {**DETAILS, "website": "example.com"}, [CERT, PHOTO], folder=tmp_path)  # bill removed
    details, documents = load_case(case_id, folder=tmp_path)
    assert details["website"] == "example.com"
    assert [d.name for d in documents] == ["cert.pdf", "passport.jpg"]
    assert len(list((tmp_path / case_id / "documents").iterdir())) == 2  # the bill's file is gone


def test_documents_are_stored_by_fingerprint_not_file_name(tmp_path):
    case_id = new_case_id()
    sneaky = UploadedDocument("../../outside.pdf", b"%PDF sneaky")
    save_case(case_id, DETAILS, [sneaky], folder=tmp_path)
    assert not (tmp_path.parent / "outside.pdf").exists()
    assert (tmp_path / case_id / "documents" / sneaky.fingerprint).exists()
    assert load_case(case_id, folder=tmp_path)[1][0].name == "../../outside.pdf"  # the name is kept, as data


def test_drafts_are_listed_newest_first(tmp_path, monkeypatch):
    first, second = "20261027-aaaaaaaa", "20261027-bbbbbbbb"
    save_case(first, DETAILS, [CERT], folder=tmp_path)
    save_case(second, {**DETAILS, "entity_name": "OTHER LTD"}, [CERT, BILL], folder=tmp_path)
    import json
    record = json.loads((tmp_path / first / "case.json").read_text())
    record["saved_at"] = "2026-01-01T09:00:00"  # make the first draft older
    (tmp_path / first / "case.json").write_text(json.dumps(record))
    drafts = list_cases(folder=tmp_path)
    assert [(d["id"], d["entity_name"], d["documents"]) for d in drafts] == [
        (second, "OTHER LTD", 2), (first, "EXAMPLE PAYMENTS LTD", 1)]


def test_no_drafts_yet(tmp_path):
    assert list_cases(folder=tmp_path / "missing") == []


def test_draft_names_cannot_point_elsewhere(tmp_path):
    for bad in ["../x", "a/b", "", "UPPER"]:
        with pytest.raises(ValueError):
            save_case(bad, DETAILS, [CERT], folder=tmp_path)


def test_answers_are_kept_inside_the_draft(tmp_path):
    case_id = new_case_id()
    paths = answer_paths(case_id, folder=tmp_path)
    assert set(paths) == {"labels", "industry", "assessment"}
    assert all(p.parent == tmp_path / case_id for p in paths.values())


def test_label_corrections_and_choice_are_kept_with_the_draft(tmp_path):
    from services.cases import load_progress, save_progress
    from services.pack import DocumentLabel
    case_id = new_case_id()
    assert load_progress(case_id, folder=tmp_path) == {}
    labels = [DocumentLabel("cert.pdf", "certificate_of_incorporation", "Registrar's certificate"),
              DocumentLabel("bill.pdf", "other", "Corrected by the reviewer")]
    save_progress(case_id, "pack-1", labels, ("payments", "fintech"), folder=tmp_path)
    assert load_progress(case_id, folder=tmp_path) == {
        "pack_key": "pack-1", "labels": labels, "choice": ("payments", "fintech")}
    save_progress(case_id, "pack-1", labels, None, folder=tmp_path)  # no choice yet
    assert load_progress(case_id, folder=tmp_path)["choice"] is None
