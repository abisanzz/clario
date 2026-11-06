from datetime import date

import pytest

import services.reviews as reviews
from services.cases import new_case_id, save_case, save_progress
from services.checklist import CHECKLISTS, load_checks
from services.cycles import (
    approved_snapshots,
    assessment_answer_path,
    copy_file,
    current_cycle,
    cycle_key,
    cycle_review_id,
    cycle_started_on,
    freeze,
    load_snapshot,
    load_submission,
    remove_snapshot,
    start_periodic_review,
    submit_for_approval,
    withdraw_submission,
)
from services.overview import all_assessments, earlier_approved_reviews
from services.pack import CheckOutcome, PackAssessment, UploadedDocument
from services.reviews import apply_overrides, approve_review, case_file, load_overrides, save_line_reviews
from services.risk import save_risk_decision
from services.validator import Status
from services.workflow import UNDER_REVIEW

CHECKS = load_checks(CHECKLISTS["fintech_high"][1])[:4]
TODAY = date(2026, 11, 1)


@pytest.fixture
def folders(tmp_path, monkeypatch):
    monkeypatch.setattr(reviews, "REVIEWS_DIR", tmp_path / "reviews")
    return tmp_path / "cases"


def checks_found() -> PackAssessment:
    """The checks before anyone's changes: the first line is Missing, the rest Present."""
    return PackAssessment([CheckOutcome(c, Status.MISSING if i == 0 else Status.PRESENT, "found")
                           for i, c in enumerate(CHECKS)])


def test_cycles_start_at_one_and_keep_their_own_files(folders):
    assert current_cycle("case", folders) == 1 and cycle_key("case", 1) == "case"
    assert start_periodic_review("case", folders, TODAY) == 2
    assert current_cycle("case", folders) == 2 and cycle_key("case", 2) == "case-cycle-2"


def test_a_review_is_submitted_only_when_every_line_is_complete(folders):
    with pytest.raises(ValueError, match="Cannot submit: 1 line"):
        submit_for_approval("case", 1, "A. Analyst", ["3.1 Missing"], folder=folders)
    with pytest.raises(ValueError, match="name"):
        submit_for_approval("case", 1, " ", [], folder=folders)
    assert load_submission("case", 1, folders) is None
    submit_for_approval("case", 1, "A. Analyst", [], folder=folders, today=TODAY)
    assert load_submission("case", 1, folders) == {"by": "A. Analyst", "on": "2026-11-01"}
    withdraw_submission("case", 1, folders)
    assert load_submission("case", 1, folders) is None


def test_the_checklist_is_frozen_at_approval(folders, tmp_path):
    lines_path = tmp_path / "lines.json"
    save_line_reviews(lines_path, checks_found(), [(CHECKS[0].id, Status.PRESENT, "Client sent it", True)],
                      "A. Analyst", TODAY)
    approved = apply_overrides(checks_found(), load_overrides(lines_path))
    freeze("case", 1, approved, "C. Head", "2026-11-01", "", "payments", "fintech_high", {"rating": "High"},
           [{"name": "cert.pdf"}], folders)
    # Later changes to the line reviews do not change what was approved
    lines_path.unlink()
    snapshot = load_snapshot("case", 1, folders)
    assert (snapshot.approved_by, snapshot.lines[0].status, snapshot.lines[0].comment) == (
        "C. Head", "Present", "Client sent it")
    assert snapshot.as_assessment().outcomes[0].validated_by == "A. Analyst, 2026-11-01"
    assert [s.cycle for s in approved_snapshots("case", folders)] == [1]
    remove_snapshot("case", 1, folders)
    assert load_snapshot("case", 1, folders) is None


def test_a_periodic_review_runs_the_checks_again_with_every_line_unvalidated(folders, tmp_path):
    assert cycle_started_on("case", folders) is None  # onboarding: the checks run as usual
    start_periodic_review("case", folders, today=TODAY)
    assert cycle_started_on("case", folders) == TODAY  # the date the checks are judged at
    assert assessment_answer_path("case", 2, folders) == folders / "case" / "assessment-cycle-2.answer.json"
    # Nothing is carried into the new cycle's line reviews, so every line starts without a Validated tick
    lines = load_overrides(case_file(cycle_key("case", 2), "fintech_high"))
    assert not any(o.validated_by for o in apply_overrides(checks_found(), lines).outcomes)
    copy_file(tmp_path / "missing.json", tmp_path / "copy.json")  # nothing to copy is fine
    assert not (tmp_path / "copy.json").exists()


def test_the_dashboard_follows_the_periodic_review(folders):
    case_id = new_case_id()
    save_case(case_id, {"source": "Upload documents", "entity_name": "EXAMPLE PAYMENTS LTD", "company_link": "",
                        "website": "", "fca_frn": ""}, [UploadedDocument("cert.pdf", b"%PDF")], folder=folders)
    save_progress(case_id, "pack", [], ("payments", "fintech_high"), folder=folders)
    save_risk_decision(case_file(case_id, "risk-decision"), "High", "High", "", "")
    approval = approve_review(case_file(case_id, "final-approval"), "C. Head", today=TODAY)
    freeze(case_id, 1, checks_found(), approval.approver, approval.approved_on, "", "payments", "fintech_high",
           {"rating": "High"}, [], folders)
    cycle = start_periodic_review(case_id, folders, TODAY)
    copy_file(case_file(case_id, "risk-decision"), case_file(cycle_key(case_id, cycle), "risk-decision"))
    summary = all_assessments(folders)[0]
    assert (summary.cycle, summary.status, summary.next_review) == (2, UNDER_REVIEW, "2027-11-01")
    # The periodic review has its own ID, linked to the original
    from services.cases import find_by_review_id, review_id
    assert summary.original_review_id == review_id(case_id)
    assert summary.review_id == cycle_review_id(case_id, 2) == review_id(case_id) + "-PR1"
    assert find_by_review_id(summary.review_id, folders) == find_by_review_id(review_id(case_id), folders) == case_id
    # The approved onboarding review is still listed in its own right, e.g. when filtering for Approved
    [earlier] = earlier_approved_reviews(folders)
    assert (earlier.review_id, earlier.status, earlier.approved_by, earlier.followed_by) == (
        review_id(case_id), "Approved", "C. Head", summary.review_id)
    assert earlier.next_action == f"Followed by {summary.review_id}" and not earlier.active


def test_approval_keeps_a_copy_of_each_document(folders):
    from services.cycles import approved_document, attach_documents, snapshot_documents_dir
    bill = UploadedDocument("bill.pdf", b"%PDF electricity bill")
    snapshot = freeze("case", 1, checks_found(), "C. Head", "2026-11-01", "", "payments", "fintech_high",
                      {"rating": "High"}, [{"name": "bill.pdf", "supports": "Original document"}], folders,
                      files={"bill.pdf": bill})
    [kept] = snapshot.documents
    assert approved_document("case", 1, kept["sha256"], folders) == bill.data  # whatever happens to the original
    # A record approved before copies were kept gets them attached, matched by name
    freeze("old", 1, checks_found(), "C. Head", "2026-10-01", "", "payments", "fintech_high", {"rating": "High"},
           [{"name": "bill.pdf"}], folders)
    assert "sha256" not in load_snapshot("old", 1, folders).documents[0]
    attached = attach_documents("old", 1, {"bill.pdf": bill}, folders)
    assert approved_document("old", 1, attached.documents[0]["sha256"], folders) == bill.data
    remove_snapshot("case", 1, folders)  # withdrawing approval removes the copies too
    assert not snapshot_documents_dir("case", 1, folders).exists()
