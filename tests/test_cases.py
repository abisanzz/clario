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
    assert set(paths) == {"labels", "industry", "assessment", "risk"}
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
        "pack_key": "pack-1", "labels": labels, "choice": ("payments", "fintech"), "comments": {}}
    save_progress(case_id, "pack-1", labels, None, folder=tmp_path)  # no choice yet
    assert load_progress(case_id, folder=tmp_path)["choice"] is None


def test_one_review_per_entity_by_company_number(tmp_path):
    from services.cases import find_case, save_review
    first = save_review(None, DETAILS, [CERT], folder=tmp_path)
    # a new review of the same company, typed differently, replaces it rather than adding another
    second = save_review(None, {**DETAILS, "entity_name": "Example Payments Limited",
                                "company_link": "https://find-and-update.company-information.service.gov.uk/company/99999901"},
                         [CERT, BILL], folder=tmp_path)
    assert second == first
    assert [(d["entity_name"], d["documents"]) for d in list_cases(folder=tmp_path)] == [("Example Payments Limited", 2)]
    assert find_case({"company_link": "99999901"}, folder=tmp_path)["id"] == first


def test_one_review_per_entity_by_name_when_there_is_no_number(tmp_path):
    from services.cases import save_review
    no_number = {**DETAILS, "company_link": "", "entity_name": "Smith & Jones Ltd"}
    first = save_review(None, no_number, [CERT], folder=tmp_path)
    assert save_review(None, {**no_number, "entity_name": "SMITH AND JONES LIMITED"}, [BILL], folder=tmp_path) == first
    other = save_review(None, {**no_number, "entity_name": "Another Ltd"}, [BILL], folder=tmp_path)
    assert other != first and len(list_cases(folder=tmp_path)) == 2


def test_older_duplicates_are_removed_when_the_entity_is_saved(tmp_path):
    from services.cases import save_review
    save_case("20261027-aaaaaaaa", DETAILS, [CERT], folder=tmp_path)  # duplicates saved before this rule existed
    save_case("20261027-bbbbbbbb", DETAILS, [BILL], folder=tmp_path)
    kept = save_review("20261027-bbbbbbbb", DETAILS, [BILL, PHOTO], folder=tmp_path)
    assert kept == "20261027-bbbbbbbb"
    assert [d["id"] for d in list_cases(folder=tmp_path)] == ["20261027-bbbbbbbb"]


def test_a_review_with_no_name_or_number_is_never_merged(tmp_path):
    from services.cases import save_review
    blank = {**DETAILS, "company_link": "", "entity_name": ""}
    assert save_review(None, blank, [CERT], folder=tmp_path) != save_review(None, blank, [BILL], folder=tmp_path)


def test_each_review_has_an_id_people_can_type(tmp_path):
    from services.cases import find_by_review_id, review_id, save_review
    case_id = save_review(None, DETAILS, [CERT], folder=tmp_path)
    rid = review_id(case_id)
    assert rid.startswith("CLR-") and len(rid) == 12
    assert list_cases(folder=tmp_path)[0]["review_id"] == rid
    for typed in (rid, rid.lower(), rid[4:], f"  {rid[4:].lower()} ", f"CLR {rid[4:]}"):
        assert find_by_review_id(typed, folder=tmp_path) == case_id, typed
    assert find_by_review_id("CLR-00000000", folder=tmp_path) is None
    assert find_by_review_id("", folder=tmp_path) is None


def test_the_id_stays_the_same_when_the_review_is_saved_again(tmp_path):
    from services.cases import review_id, save_review
    first = save_review(None, DETAILS, [CERT], folder=tmp_path)
    again = save_review(None, {**DETAILS, "website": "example.com"}, [CERT, BILL], folder=tmp_path)
    assert review_id(again) == review_id(first)


def test_only_the_latest_review_of_each_entity_is_shown_and_older_ones_can_be_removed(tmp_path):
    import json
    from services.cases import latest_reviews, remove_duplicates
    save_case("20261027-aaaaaaaa", DETAILS, [CERT], folder=tmp_path)            # saved before the one-review rule
    save_case("20261027-bbbbbbbb", DETAILS, [BILL], folder=tmp_path)
    save_case("20261027-cccccccc", {**DETAILS, "company_link": "12345678"}, [CERT], folder=tmp_path)
    record = json.loads((tmp_path / "20261027-aaaaaaaa" / "case.json").read_text())
    record["saved_at"] = "2026-01-01T09:00:00"
    (tmp_path / "20261027-aaaaaaaa" / "case.json").write_text(json.dumps(record))
    assert sorted(d["id"] for d in latest_reviews(folder=tmp_path)) == ["20261027-bbbbbbbb", "20261027-cccccccc"]
    assert remove_duplicates(folder=tmp_path) == ["20261027-aaaaaaaa"]
    assert not (tmp_path / "20261027-aaaaaaaa").exists()
    assert len(list_cases(folder=tmp_path)) == 2


def test_supporting_documents_join_the_document_store_and_survive_resaving(tmp_path):
    from services.cases import add_supporting_document, load_supporting
    case_id = new_case_id()
    save_case(case_id, DETAILS, [CERT], folder=tmp_path)
    wealth = UploadedDocument("source_of_wealth.pdf", b"%PDF wealth")
    add_supporting_document(case_id, wealth, "3.6", "A. Analyst", folder=tmp_path)
    [(document, record)] = load_supporting(case_id, folder=tmp_path)
    assert document == wealth
    assert (record["check_id"], record["added_by"]) == ("3.6", "A. Analyst")
    save_case(case_id, {**DETAILS, "website": "example.com"}, [CERT, BILL], folder=tmp_path)  # details re-saved
    assert [d.name for d, _ in load_supporting(case_id, folder=tmp_path)] == ["source_of_wealth.pdf"]
    assert (tmp_path / case_id / "documents" / wealth.fingerprint).exists()
    assert [d.name for d in load_case(case_id, folder=tmp_path)[1]] == ["cert.pdf", "bill.pdf"]


def test_document_descriptions_are_kept_with_the_draft(tmp_path):
    case_id = new_case_id()
    described = UploadedDocument("cert.pdf", b"%PDF cert", description="Certificate of incorporation, 2019")
    save_case(case_id, DETAILS, [described], folder=tmp_path)
    assert load_case(case_id, folder=tmp_path)[1][0].description == "Certificate of incorporation, 2019"


def test_a_supporting_document_can_be_deleted(tmp_path):
    from services.cases import add_supporting_document, load_supporting, remove_supporting_document
    case_id = new_case_id()
    save_case(case_id, DETAILS, [CERT], folder=tmp_path)
    wealth = UploadedDocument("source_of_wealth.pdf", b"%PDF wealth")
    add_supporting_document(case_id, wealth, "3.6", folder=tmp_path)
    remove_supporting_document(case_id, wealth.fingerprint, folder=tmp_path)
    assert load_supporting(case_id, folder=tmp_path) == []
    assert not (tmp_path / case_id / "documents" / wealth.fingerprint).exists()
    assert (tmp_path / case_id / "documents" / CERT.fingerprint).exists()  # the original documents stay


def test_document_comments_are_kept_with_the_draft(tmp_path):
    from services.cases import load_progress, save_progress
    case_id = new_case_id()
    save_progress(case_id, "pack-1", [], None, folder=tmp_path, comments={"bill.pdf": "Older than 3 months"})
    assert load_progress(case_id, folder=tmp_path)["comments"] == {"bill.pdf": "Older than 3 months"}
