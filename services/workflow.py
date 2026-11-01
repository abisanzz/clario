"""The status of a KYC assessment.

Most statuses follow from the work done (In Progress, Under Review, Pending Approval, Approved, and Not Started when
an approved assessment's next review is due within six months). Rejected, On Hold and Cancelled are set by a person,
with a reason, and take priority in that order.
"""

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

NOT_STARTED, IN_PROGRESS, UNDER_REVIEW = "Not Started", "In Progress", "Under Review"
PENDING_APPROVAL, APPROVED, REJECTED = "Pending Approval", "Approved", "Rejected"
ON_HOLD, CANCELLED = "On Hold", "Cancelled"
STATUSES = [NOT_STARTED, IN_PROGRESS, UNDER_REVIEW, PENDING_APPROVAL, APPROVED, REJECTED, ON_HOLD, CANCELLED]
SET_BY_A_PERSON = (CANCELLED, REJECTED, ON_HOLD)  # in order of priority

DEFINITIONS = {
    NOT_STARTED: "A KYC review is due within the next six months but has not yet been started.",
    IN_PROGRESS: "Documents are being collected, processed and assessed by the AI agent and/or analyst.",
    UNDER_REVIEW: "An analyst is reviewing the findings, supporting evidence, discrepancies and risk indicators.",
    PENDING_APPROVAL: "The review is complete, submitted, and awaiting formal sign-off from an authorised approver.",
    APPROVED: "The required due diligence checks are complete and formally approved.",
    REJECTED: "The assessment failed to meet the required due diligence standards and was formally rejected.",
    ON_HOLD: "Paused because of an unresolved issue, outstanding dependency or business decision.",
    CANCELLED: "Formally discontinued and will not proceed, e.g. the request was withdrawn or is a duplicate.",
}
REVIEW_YEARS = {"Low": 3, "Medium": 2, "High": 1}  # review frequency from the risk methodology
REVIEW_DUE_WARNING_DAYS = 183  # about six months


@dataclass(frozen=True)
class StatusChange:
    status: str  # Rejected, On Hold or Cancelled
    reason: str
    by: str
    on: str  # YYYY-MM-DD


def set_status(path: Path, status: str, reason: str, by: str, today: date | None = None) -> StatusChange:
    """Set a status that a person decides (Rejected, On Hold or Cancelled). A reason and a name are required."""
    if status not in SET_BY_A_PERSON:
        raise ValueError(f"{status} is worked out automatically and cannot be set by hand")
    if not reason.strip():
        raise ValueError(f"Give a reason for marking the assessment {status}")
    if not by.strip():
        raise ValueError("Give your name")
    change = StatusChange(status, reason.strip(), by.strip(), (today or date.today()).isoformat())
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(asdict(change), indent=2))
    return change


def load_status(path: Path) -> StatusChange | None:
    return StatusChange(**json.loads(path.read_text())) if path.exists() else None


def clear_status(path: Path) -> None:
    """Resume an assessment that was on hold (or undo a rejection): its status follows the work again."""
    path.unlink(missing_ok=True)


def next_review_date(approved_on: str, rating: str) -> date:
    approved = date.fromisoformat(approved_on)
    years = REVIEW_YEARS.get(rating, 1)
    try:
        return approved.replace(year=approved.year + years)
    except ValueError:  # 29 February
        return approved.replace(year=approved.year + years, day=28)


def work_out_status(manual: StatusChange | None, approved_on: str | None, rating: str, risk_decided: bool,
                    lines: int, validated: int, today: date | None = None, submitted: bool = False) -> str:
    """The assessment's status: a person's decision first, then what the work so far shows. `validated` counts the
    lines that are complete (Present and validated). Pending Approval means every line is, and the analyst has
    submitted the review for approval."""
    if manual:
        return manual.status
    if approved_on:
        due = next_review_date(approved_on, rating)
        return NOT_STARTED if (due - (today or date.today())).days <= REVIEW_DUE_WARNING_DAYS else APPROVED
    if not risk_decided:
        return IN_PROGRESS
    if submitted and lines and validated >= lines:
        return PENDING_APPROVAL
    return UNDER_REVIEW
