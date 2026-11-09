import pytest

from services.demo import DEMO_NOTE, is_demo
from services.extractor import ExtractionFailed, make_client, saved_or_ask


def test_the_demo_is_off_unless_switched_on(monkeypatch):
    monkeypatch.delenv("CLARIO_DEMO", raising=False)
    assert not is_demo()
    for value in ("true", "1", "Yes", " TRUE "):
        monkeypatch.setenv("CLARIO_DEMO", value)
        assert is_demo(), value
    for value in ("", "false", "0", "no"):
        monkeypatch.setenv("CLARIO_DEMO", value)
        assert not is_demo(), value


def test_the_demo_never_connects_to_claude_even_with_a_key(monkeypatch):
    monkeypatch.setenv("CLARIO_DEMO", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")
    with pytest.raises(ExtractionFailed, match="public demo"):
        make_client()
    assert "never calls the AI service" in DEMO_NOTE


def test_saved_answers_still_replay_in_the_demo(monkeypatch, tmp_path):
    import json
    monkeypatch.setenv("CLARIO_DEMO", "true")
    saved = tmp_path / "labels.answer.json"
    saved.write_text(json.dumps({"input_sha256": "same input", "answer": {"files": []}}))

    def ask():
        return {"files": []}, make_client()  # would be refused: a saved answer must mean it is never asked

    assert saved_or_ask(saved, "same input", ask) == ({"files": []}, None, True)
    with pytest.raises(ExtractionFailed):
        saved_or_ask(saved, "different input", ask)  # anything new stops with the demo message


@pytest.fixture
def spaces(tmp_path, monkeypatch):
    """The demo's folders in a temporary place, and no visitor once the test ends."""
    import services.cases as cases
    import services.cycles as cycles
    import services.reviews as reviews
    from services.demo import use_visitor_from
    monkeypatch.setattr(cases, "CASES_DIR", tmp_path / "cases")
    monkeypatch.setattr(cycles, "CASES_DIR", tmp_path / "cases")
    monkeypatch.setattr(reviews, "REVIEWS_DIR", tmp_path / "reviews")
    yield tmp_path
    use_visitor_from(None)


def test_only_codes_clario_makes_are_accepted():
    from services.demo import is_visitor_code, new_visitor_code
    assert is_visitor_code(new_visitor_code())
    for bad in ("", "../../etc", "0123456789ABCDEF", "0123456789abcde", "0123456789abcdef0", "0123456789abcdeg"):
        assert not is_visitor_code(bad), bad


def test_each_visitor_starts_with_no_saved_reviews_and_never_sees_another(spaces):
    from services.cases import find_case, list_cases, save_review
    from services.demo import use_visitor_from
    from services.pack import UploadedDocument
    details = {"source": "Sample pack", "entity_name": "EXAMPLE PAYMENTS LTD", "company_link": "99999901"}
    visitor = {"code": "a" * 16}
    use_visitor_from(lambda: visitor["code"])
    first = save_review(None, details, [UploadedDocument("cert.pdf", b"%PDF")])
    assert [d["id"] for d in list_cases()] == [first]
    assert (spaces / "cases" / "visitors" / ("a" * 16) / first).exists()
    from services.audit import log_event
    from services.reviews import case_file
    log_event(case_file(first, "audit").with_suffix(".jsonl"), "A. Visitor", "Started")  # its folders are made
    assert case_file(first, "audit").parent == spaces / "reviews" / "visitors" / ("a" * 16)
    visitor["code"] = "b" * 16  # someone else
    assert list_cases() == [] and find_case(details) is None  # a first-time visitor: nothing saved yet
    second = save_review(None, details, [UploadedDocument("cert.pdf", b"%PDF")])
    assert second != first  # their review does not replace the first visitor's
    visitor["code"] = "a" * 16
    assert [d["id"] for d in list_cases()] == [first]


def test_outside_the_demo_the_normal_folders_are_used(spaces):
    import services.cases as cases
    from services.demo import use_visitor_from, visitor_space
    use_visitor_from(None)
    assert visitor_space(cases.CASES_DIR) == spaces / "cases"
    use_visitor_from(lambda: "../not-a-code")  # a code that is not valid is never used as a folder
    assert visitor_space(cases.CASES_DIR) == spaces / "cases"


def test_spaces_nobody_has_used_for_a_day_are_cleared(tmp_path):
    import os
    import time
    from services.demo import clear_old_visitors
    old, recent = tmp_path / "visitors" / ("a" * 16), tmp_path / "visitors" / ("b" * 16)
    for space in (old, recent):
        (space / "review").mkdir(parents=True)
        (space / "review" / "case.json").write_text("{}")
    (tmp_path / "visitors" / "not-a-visitor").mkdir()
    two_days_ago = time.time() - 48 * 3600
    for path in [old, *old.rglob("*")]:
        os.utime(path, (two_days_ago, two_days_ago))
    assert clear_old_visitors([tmp_path]) == ["a" * 16]
    assert not old.exists() and recent.exists() and (tmp_path / "visitors" / "not-a-visitor").exists()


def test_the_demo_never_looks_up_the_registers(monkeypatch):
    """The example's numbers are fictional: in the demo both registers answer "not found" without going online,
    so an outage can't change what Clario reads."""
    import urllib.request

    from services.companies_house import CompanyNotFound, get_company
    from services.fca import FirmNotFound, get_firm
    from services.pack import companies_house_source, fca_source

    def no_internet(*args, **kwargs):
        raise AssertionError("the demo went online")
    monkeypatch.setattr(urllib.request, "urlopen", no_internet)
    monkeypatch.setenv("CLARIO_DEMO", "true")
    with pytest.raises(CompanyNotFound):
        get_company("99999901")
    with pytest.raises(FirmNotFound):
        get_firm("999999")
    assert companies_house_source("99999901").text == (
        "There is no company with number 99999901 on the Companies House register.")
    assert fca_source("999999").text == (
        "There is no firm with reference number 999999 on the FCA Financial Services Register.")
