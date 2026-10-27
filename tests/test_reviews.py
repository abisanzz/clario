from datetime import date

import pytest

from services.checklist import load_checks
from services.pack import CheckOutcome, PackAssessment
from services.reviews import apply_overrides, case_file, load_overrides, remove_override, save_override
from services.validator import Status

CHECKS = {c.id: c for c in load_checks()}
TODAY = date(2026, 10, 22)
ASSESSMENT = PackAssessment([
    CheckOutcome(CHECKS["3.1"], Status.MISSING, "No ownership chart", decided_by="Claude"),
    CheckOutcome(CHECKS["3.2"], Status.UNCLEAR, "25% on register, 28% in questionnaire", decided_by="Claude"),
    CheckOutcome(CHECKS["6.1"], Status.NOT_STARTED, "Needs a screening tool", decided_by="Screening tool"),
])


@pytest.fixture
def path(tmp_path):
    return case_file("pack-fingerprint", "fintech", folder=tmp_path)


def change(path, check_id="3.2", status=Status.PRESENT, note="Client confirmed 25%; questionnaire was a typo",
           reviewer="A. Analyst"):
    return save_override(path, ASSESSMENT, check_id, status, note, reviewer, today=TODAY)


def test_a_change_is_saved_and_comes_back(path):
    change(path)
    saved = load_overrides(path)["3.2"]
    assert (saved.status, saved.reviewer, saved.reviewed_on) == (Status.PRESENT, "A. Analyst", "2026-10-22")
    assert (saved.original_status, saved.original_finding, saved.original_decided_by) == (
        Status.UNCLEAR, "25% on register, 28% in questionnaire", "Claude")


def test_results_follow_the_analyst(path):
    change(path)
    change(path, "6.1", Status.PRESENT, "Screened in World-Check, no matches")
    result = apply_overrides(ASSESSMENT, load_overrides(path))
    reviewed = result.outcomes[1]
    assert reviewed.status is Status.PRESENT
    assert reviewed.finding == "Client confirmed 25%; questionnaire was a typo"
    assert reviewed.decided_by == "Analyst: A. Analyst, 2026-10-22"
    assert reviewed.before_review == "Unclear (Claude): 25% on register, 28% in questionnaire"
    assert result.count(Status.PRESENT) == 2 and result.count(Status.NOT_STARTED) == 0
    assert [o.check.id for o in result.request_from_client()] == ["3.1"]
    assert result.outcomes[0] == ASSESSMENT.outcomes[0]  # unchanged checks stay as they were


def test_a_reason_and_a_reviewer_are_required(path):
    with pytest.raises(ValueError, match="reason"):
        change(path, note="  ")
    with pytest.raises(ValueError, match="reviewer"):
        change(path, reviewer="")
    assert not path.exists()


def test_undo_brings_back_the_original(path):
    change(path)
    change(path, "3.1", Status.NEEDS_HUMAN_REVIEW, "Chart requested by email")
    remove_override(path, "3.2")
    assert list(load_overrides(path)) == ["3.1"]
    assert apply_overrides(ASSESSMENT, load_overrides(path)).outcomes[1] == ASSESSMENT.outcomes[1]


def test_the_latest_change_wins(path):
    change(path)
    change(path, status=Status.MISSING, note="Client could not confirm")
    assert load_overrides(path)["3.2"].status is Status.MISSING


def test_each_case_has_its_own_file(tmp_path):
    fintech = case_file("pack-fingerprint", "fintech", folder=tmp_path)
    assert fintech != case_file("pack-fingerprint", "crypto", folder=tmp_path)
    assert fintech != case_file("other-pack", "fintech", folder=tmp_path)
    assert load_overrides(fintech) == {}


def test_a_line_can_be_validated_without_changing_it(path):
    from services.reviews import save_line_reviews
    assert save_line_reviews(path, ASSESSMENT, [("3.1", Status.MISSING, "", True)], "A. Analyst", today=TODAY) == []
    result = apply_overrides(ASSESSMENT, load_overrides(path))
    line = result.outcomes[0]
    assert (line.status, line.finding, line.decided_by) == (Status.MISSING, "No ownership chart", "Claude")
    assert line.validated_by == "A. Analyst, 2026-10-22"
    assert line.before_review == ""  # nothing was changed


def test_changing_a_status_in_the_table_needs_a_note_and_saves_nothing_until_it_has_one(path):
    from services.reviews import save_line_reviews
    lines = [("3.1", Status.MISSING, "", True), ("3.2", Status.PRESENT, "", True)]
    assert save_line_reviews(path, ASSESSMENT, lines, "A. Analyst", today=TODAY) == [
        "3.2: give a reason for changing the status to Present"]
    assert load_overrides(path) == {}  # nothing saved, not even the valid line
    lines[1] = ("3.2", Status.PRESENT, "Client confirmed 25%", True)
    assert save_line_reviews(path, ASSESSMENT, lines, "A. Analyst", today=TODAY) == []
    changed = apply_overrides(ASSESSMENT, load_overrides(path)).outcomes[1]
    assert (changed.status, changed.finding, changed.validated_by) == (
        Status.PRESENT, "Client confirmed 25%", "A. Analyst, 2026-10-22")


def test_the_table_needs_a_reviewer_name(path):
    from services.reviews import save_line_reviews
    assert save_line_reviews(path, ASSESSMENT, [("3.1", Status.MISSING, "", True)], "  ") == ["Give the reviewer's name"]


def test_unticking_a_validated_line_removes_its_review(path):
    from services.reviews import save_line_reviews
    save_line_reviews(path, ASSESSMENT, [("3.1", Status.MISSING, "", True)], "A. Analyst", today=TODAY)
    save_line_reviews(path, ASSESSMENT, [("3.1", Status.MISSING, "", False)], "A. Analyst", today=TODAY)
    assert load_overrides(path) == {}


def test_reviews_saved_before_validation_existed_still_load(path):
    import json
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"3.2": {
        "check_id": "3.2", "status": "Present", "note": "Confirmed", "reviewer": "A. Analyst",
        "reviewed_on": "2026-10-22", "original_status": "Unclear", "original_finding": "x",
        "original_decided_by": "Claude"}}))
    assert load_overrides(path)["3.2"].validated is False
