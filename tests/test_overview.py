import pytest

import services.reviews as reviews
from services.cases import new_case_id, save_case, save_progress
from services.cycles import submit_for_approval
from services.checklist import CHECKLISTS, load_checks
from services.overview import all_assessments
from services.workflow import APPROVED, IN_PROGRESS, ON_HOLD, PENDING_APPROVAL, UNDER_REVIEW, set_status
from services.pack import CheckOutcome, PackAssessment, UploadedDocument
from services.reviews import approve_review, case_file, save_line_reviews
from services.risk import save_risk_decision
from services.validator import Status

DETAILS = {"source": "Upload documents", "entity_name": "EXAMPLE PAYMENTS LTD", "company_link": "99999901",
           "website": "", "fca_frn": ""}
REVIEWED = [c for c in load_checks(CHECKLISTS["fintech_high"][1]) if c.section[:2] in ("1.", "2.", "3.", "4.", "5.", "6.")]


@pytest.fixture
def folders(tmp_path, monkeypatch):
    monkeypatch.setattr(reviews, "REVIEWS_DIR", tmp_path / "reviews")
    return tmp_path / "cases"


def make_case(folders, rated=True, validated=0):
    case_id = new_case_id()
    save_case(case_id, DETAILS, [UploadedDocument("cert.pdf", b"%PDF")], folder=folders)
    if rated:
        save_progress(case_id, "pack", [], ("payments", "fintech_high"), folder=folders)
        save_risk_decision(case_file(case_id, "risk-decision"), "High", "High", "", "")
    assessment = PackAssessment([CheckOutcome(c, Status.PRESENT, "ok") for c in REVIEWED])
    lines = [(c.id, Status.PRESENT, "", True) for c in REVIEWED[:validated]]
    if lines:
        save_line_reviews(case_file(case_id, "fintech_high"), assessment, lines, "A. Analyst")
    return case_id


def test_a_new_case_is_in_progress(folders):
    make_case(folders, rated=False)
    [summary] = all_assessments(folders)
    assert (summary.status, summary.risk, summary.checklist, summary.lines) == (IN_PROGRESS, "", "", 0)
    assert summary.review_id.startswith("CLR-") and summary.entity_name == "EXAMPLE PAYMENTS LTD"


def test_progress_and_status_follow_the_review(folders):
    case_id = make_case(folders, validated=3)
    summary = all_assessments(folders)[0]
    assert (summary.status, summary.risk, summary.validated, summary.lines) == (UNDER_REVIEW, "High", 3, len(REVIEWED))
    assert summary.industry.startswith("Payments") and summary.checklist.endswith("High risk")
    assert summary.needs_attention  # high risk, not yet approved
    approve_review(case_file(case_id, "final-approval"), "C. Head")
    approved = all_assessments(folders)[0]
    assert (approved.status, approved.approved_by, approved.needs_attention) == (APPROVED, "C. Head", False)
    assert approved.next_review  # a year after approval, for a high-risk client


def test_pending_approval_once_every_line_is_validated_and_submitted(folders):
    case_id = make_case(folders, validated=len(REVIEWED))
    ready = all_assessments(folders)[0]
    assert (ready.status, ready.next_action) == (UNDER_REVIEW, "Submit for approval")
    submit_for_approval(case_id, 1, "A. Analyst", [], folder=folders)
    assert all_assessments(folders)[0].status == PENDING_APPROVAL


def test_a_person_can_put_it_on_hold(folders):
    case_id = make_case(folders, validated=3)
    set_status(case_file(case_id, "status"), ON_HOLD, "Waiting for the ownership chart", "A. Analyst")
    summary = all_assessments(folders)[0]
    assert (summary.status, summary.status_reason, summary.needs_attention) == (
        ON_HOLD, "Waiting for the ownership chart", True)


def test_next_action_follows_the_status(folders):
    make_case(folders, validated=3)
    summary = all_assessments(folders)[0]
    assert summary.next_action == f"Validate {len(REVIEWED) - 3} checklist lines" and summary.active


def test_recent_activity_combines_every_assessment_newest_first(folders):
    from datetime import datetime
    from services.audit import log_event
    from services.overview import AI_PROCESSING, ANALYST_ACTION, CREATION, DOCUMENT_UPLOAD, recent_activity
    first = make_case(folders, rated=False)
    path = case_file(first, "audit").with_suffix(".jsonl")
    log_event(path, "A. Analyst", "Created the assessment", when=datetime(2026, 11, 1, 9, 0))
    log_event(path, "A. Analyst", "Uploaded document cert.pdf", when=datetime(2026, 11, 1, 9, 1))
    log_event(path, "Clario", "Identified 1 document", when=datetime(2026, 11, 1, 9, 2))
    log_event(path, "B. Reviewer", "Status Unclear → Present", "3.2", when=datetime(2026, 11, 1, 9, 3))
    activity = recent_activity(folder=folders)
    assert [a.kind for a in activity] == [ANALYST_ACTION, AI_PROCESSING, DOCUMENT_UPLOAD, CREATION]
    assert activity[0].entity_name == "EXAMPLE PAYMENTS LTD" and activity[0].line == "3.2"
    assert len(recent_activity(limit=2, folder=folders)) == 2


def test_validated_but_missing_lines_are_not_ready_for_approval(folders):
    case_id = make_case(folders, validated=0)
    assessment = PackAssessment([CheckOutcome(c, Status.MISSING, "not provided") for c in REVIEWED])
    lines = [(c.id, Status.MISSING, "", True) for c in REVIEWED]  # all validated, but still Missing
    save_line_reviews(case_file(case_id, "fintech_high"), assessment, lines, "A. Analyst")
    assert all_assessments(folders)[0].status == UNDER_REVIEW


def test_older_assessments_take_their_owner_from_the_audit_log(folders):
    from services.audit import log_event
    case_id = make_case(folders, rated=False)
    assert all_assessments(folders)[0].owner == "Unassigned"
    log_event(case_file(case_id, "audit").with_suffix(".jsonl"), "A. Analyst", "Created the assessment for X")
    assert all_assessments(folders)[0].owner == "A. Analyst"


def test_rejected_cancelled_and_approved_assessments_are_not_active(folders):
    from services.workflow import CANCELLED, REJECTED
    case_id = make_case(folders, validated=3)
    assert all_assessments(folders)[0].active
    for status in (REJECTED, CANCELLED):
        set_status(case_file(case_id, "status"), status, "Reason", "Abi San")
        assert not all_assessments(folders)[0].active
