import json

from services.intelligence import key_facts, normalise, owners, people
from services.pack import DocumentDetails, DocumentLabel, Identification, UploadedDocument, extract_details, identify_documents
from tests.fakes import FakeClaude

PACK = [UploadedDocument("cert.pdf", b"%PDF certificate"), UploadedDocument("register.pdf", b"%PDF register")]


def file(number, kind, name="", number_="", address="", date="", people_=(), owners_=()):
    return {"file_number": number, "document_type": kind, "reason": "Because", "company_name": name,
            "registration_number": number_, "registered_address": address, "document_date": date,
            "people": [{"name": n, "role": r} for n, r in people_],
            "owners": [{"name": n, "share": s} for n, s in owners_]}


REPLY = {"files": [
    file(1, "certificate_of_incorporation", "EXAMPLE PAYMENTS LIMITED", "09999901", "1 High St, London",
         "2019-03-14"),
    file(2, "register_of_shareholders", "Example Payments Ltd", "9999901", "2 Low Road, Leeds", "",
         [("Jane Doe", "Director"), ("Jane Doe", "Shareholder")], [("Holdco Ltd", "75%"), ("Jane Doe", "25%")]),
]}


def test_identification_extracts_each_documents_details():
    result = identify_documents(PACK, client=FakeClaude(REPLY))
    assert result.extracted and result.labels[1].document_type == "register_of_shareholders"
    register = result.details["register.pdf"]
    assert (register.company_name, register.people[0], register.owners[0]) == (
        "Example Payments Ltd", ("Jane Doe", "Director"), ("Holdco Ltd", "75%"))
    assert result.details["cert.pdf"].document_date == "2019-03-14"


def test_an_answer_saved_before_extraction_still_replays(tmp_path):
    saved = tmp_path / "labels.answer.json"
    old = {"files": [{"file_number": 1, "document_type": "certificate_of_incorporation", "reason": "Old"},
                     {"file_number": 2, "document_type": "other", "reason": "Old"}]}
    from services.pack import pack_fingerprint
    saved.write_text(json.dumps({"input_sha256": pack_fingerprint(PACK), "model": "m", "answer": old}))
    result = identify_documents(PACK, saved_answer=saved)
    assert result.replayed and not result.extracted and result.details == {}


def test_extracting_details_later_keeps_the_document_types(tmp_path):
    saved = tmp_path / "labels.answer.json"
    before = Identification([DocumentLabel("cert.pdf", "certificate_of_incorporation", "Old reason"),
                             DocumentLabel("register.pdf", "other", "Old reason")])
    after = extract_details(PACK, before, saved, client=FakeClaude(REPLY))
    assert after.labels == before.labels and after.extracted
    assert after.details["register.pdf"].owners == [("Holdco Ltd", "75%"), ("Jane Doe", "25%")]
    # The saved answer now has the details, with the same types, so it replays for free next time
    replayed = identify_documents(PACK, saved_answer=saved)
    assert replayed.replayed and replayed.labels == before.labels and replayed.details == after.details


def test_key_facts_flag_where_the_documents_disagree():
    details = identify_documents(PACK, client=FakeClaude(REPLY)).details
    facts = {f.fact: f for f in key_facts(details)}
    assert not facts["Company name"].disagree  # "LIMITED" and "Ltd" are the same name
    assert not facts["Registration number"].disagree  # a leading zero is the same number
    assert facts["Registered address"].disagree
    assert facts["Registered address"].values == {"1 High St, London": ["cert.pdf"],
                                                  "2 Low Road, Leeds": ["register.pdf"]}
    assert people(details) == [("Jane Doe", ["Director", "Shareholder"], ["register.pdf"])]
    assert owners(details)[0] == ("Holdco Ltd", {"75%": ["register.pdf"]})


def test_normalising_names():
    assert normalise("Example Payments Limited.") == normalise("EXAMPLE  PAYMENTS LTD")
    assert DocumentDetails().empty and not DocumentDetails(company_name="X").empty


def test_an_fca_firm_reference_is_not_compared_as_a_company_number():
    details = {"cert.pdf": DocumentDetails("Sterling Asset Management Limited", "CLARIO-TEST-001"),
               "fca.pdf": DocumentDetails("Sterling Asset Management Limited", "CLARIO-FRN-TEST-001")}
    numbers = {f.fact: f for f in key_facts(details)}["Registration number"]
    assert not numbers.disagree and numbers.values == {"CLARIO-TEST-001": ["cert.pdf"]}


def test_shares_are_compared_by_their_percentage():
    from services.intelligence import percentage
    assert percentage("600 ordinary shares (60%)") == percentage("60 %") == "60%"
    details = {"register.pdf": DocumentDetails(owners=[("Amelia Hart", "600 ordinary shares (60%)")]),
               "psc.pdf": DocumentDetails(owners=[("Amelia Hart", "60%")])}
    assert owners(details) == [("Amelia Hart", {"60%": ["register.pdf", "psc.pdf"]})]
