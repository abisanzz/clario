from datetime import date

import pytest

from services.workflow import (
    APPROVED,
    CANCELLED,
    IN_PROGRESS,
    NOT_STARTED,
    ON_HOLD,
    PENDING_APPROVAL,
    REJECTED,
    UNDER_REVIEW,
    clear_status,
    load_status,
    next_review_date,
    set_status,
    work_out_status,
)

TODAY = date(2026, 11, 1)


def status(manual=None, approved_on=None, rating="High", risk_decided=True, lines=28, validated=0, submitted=True):
    return work_out_status(manual, approved_on, rating, risk_decided, lines, validated, today=TODAY,
                           submitted=submitted)


def test_statuses_that_follow_the_work():
    assert status(risk_decided=False) == IN_PROGRESS
    assert status(validated=10) == UNDER_REVIEW
    assert status(validated=28) == PENDING_APPROVAL
    assert status(validated=28, submitted=False) == UNDER_REVIEW  # complete, but not yet submitted
    assert status(validated=10, submitted=True) == UNDER_REVIEW  # changed after it was submitted
    assert status(approved_on="2026-10-31", rating="Low") == APPROVED


def test_an_approved_assessment_becomes_not_started_when_its_review_is_near():
    assert next_review_date("2026-01-15", "High") == date(2027, 1, 15)
    assert status(approved_on="2026-01-15", rating="High") == NOT_STARTED  # due in about 2.5 months
    assert status(approved_on="2026-01-15", rating="Medium") == APPROVED  # due in 2028
    assert next_review_date("2024-02-29", "Medium") == date(2026, 2, 28)


def test_statuses_set_by_a_person_take_priority(tmp_path):
    path = tmp_path / "status.json"
    for chosen in (ON_HOLD, REJECTED, CANCELLED):
        change = set_status(path, chosen, "Waiting for the client", "A. Analyst", today=TODAY)
        assert status(manual=load_status(path), validated=28) == chosen
        assert (change.by, change.on) == ("A. Analyst", "2026-11-01")
    clear_status(path)
    assert load_status(path) is None


def test_setting_a_status_needs_a_reason_and_a_name(tmp_path):
    path = tmp_path / "status.json"
    with pytest.raises(ValueError, match="reason"):
        set_status(path, ON_HOLD, " ", "A. Analyst")
    with pytest.raises(ValueError, match="name"):
        set_status(path, ON_HOLD, "Waiting", "")
    with pytest.raises(ValueError, match="worked out automatically"):
        set_status(path, APPROVED, "x", "A. Analyst")
    assert load_status(path) is None
