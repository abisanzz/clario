"""A summary of each saved KYC assessment, for the dashboard and the case list. Reads only what is already saved."""

from dataclasses import dataclass, replace
from pathlib import Path

from services.audit import NO_NAME, load_events
from services.cases import latest_reviews, load_progress
from services.checklist import CHECKLISTS, load_checks
from services.cycles import approved_snapshots, current_cycle, cycle_key, cycle_review_id, load_submission
from services.industry import INDUSTRIES
from services.reviews import case_file, load_approval, load_overrides
from services.risk import load_risk_decision
from services.validator import Status
from services.workflow import (
    APPROVED,
    IN_PROGRESS,
    NOT_STARTED,
    ON_HOLD,
    PENDING_APPROVAL,
    UNDER_REVIEW,
    load_status,
    next_review_date,
    work_out_status,
)

# Sections reviewed before approval (section 7 is covered by the risk rating and approval; 8 comes after approval)
REVIEWED_BEFORE_APPROVAL = ("1.", "2.", "3.", "4.", "5.", "6.")



@dataclass(frozen=True)
class AssessmentSummary:
    case_id: str
    review_id: str
    entity_name: str
    company: str
    industry: str  # name, or "" before it is confirmed
    checklist: str  # name, or ""
    risk: str  # "Low", "Medium", "High", or ""
    validated: int  # lines validated so far
    lines: int  # lines to validate before approval
    status: str
    approved_by: str
    saved_at: str
    status_reason: str = ""  # why it was rejected, put on hold or cancelled
    next_review: str = ""  # YYYY-MM-DD, once approved
    cycle: int = 1  # 1 for onboarding, then one more for each periodic review
    ready: bool = False  # every line is Present and validated, so it can be submitted for approval
    owner: str = ""  # whoever created the assessment, or the analyst it was reassigned to
    last_activity: str = ""  # YYYY-MM-DD HH:MM of the latest change of any kind
    original_review_id: str = ""  # the onboarding review's ID; review_id is the current cycle's own ID
    followed_by: str = ""  # for an earlier approved review: the ID of the periodic review that followed it

    @property
    def next_action(self) -> str:
        """What needs doing next, in a few words."""
        if self.followed_by:
            return f"Followed by {self.followed_by}"
        return {
            NOT_STARTED: "Start the periodic review",
            IN_PROGRESS: "Confirm the industry and risk rating",
            UNDER_REVIEW: ("Submit for approval" if self.ready else
                           f"Validate {self.lines - self.validated} checklist lines" if self.lines
                           else "Review the checklist"),
            PENDING_APPROVAL: "Senior management approval",
            ON_HOLD: "Resolve the hold",
        }.get(self.status, "None")

    @property
    def active(self) -> bool:
        """Still being worked on. Approved, rejected and cancelled assessments are not active."""
        return self.status in (NOT_STARTED, IN_PROGRESS, UNDER_REVIEW, PENDING_APPROVAL, ON_HOLD)

    @property
    def needs_attention(self) -> bool:
        """Waiting for approval, on hold, due for its periodic review, or high risk and still being worked on."""
        return (self.status in (PENDING_APPROVAL, ON_HOLD, NOT_STARTED)
                or self.risk == "High" and self.status in (IN_PROGRESS, UNDER_REVIEW))


def summarise(draft: dict, folder: Path | None = None) -> AssessmentSummary:
    """One assessment's progress, worked out from its saved files."""
    case_id = draft["id"]
    progress = load_progress(case_id, folder=folder)
    industry_key, checklist_key = (progress.get("choice") or (None, None))
    cycle = current_cycle(case_id, folder)
    key = cycle_key(case_id, cycle)  # this review cycle's files
    decision = load_risk_decision(case_file(key, "risk-decision"))
    # The rating counts only with an industry and checklist confirmed for the current documents: when the documents
    # change, that choice is cleared to be confirmed again, and a rating saved before then no longer applies
    rating = decision.rating if decision and checklist_key else ""
    approval = load_approval(case_file(key, "final-approval"))
    lines, validated, complete = 0, 0, 0
    if checklist_key in CHECKLISTS:
        reviewed = {c.id for c in load_checks(CHECKLISTS[checklist_key][1])
                    if c.section.startswith(REVIEWED_BEFORE_APPROVAL)}
        lines = len(reviewed)
        overrides = load_overrides(case_file(key, checklist_key))
        validated = sum(1 for check_id, o in overrides.items() if o.validated and check_id in reviewed)
        # complete = validated and Present (a validated line keeps the status it had when it was saved)
        complete = sum(1 for check_id, o in overrides.items()
                       if o.validated and o.status is Status.PRESENT and check_id in reviewed)
    manual = load_status(case_file(case_id, "status"))
    submitted = load_submission(case_id, cycle, folder) is not None
    status = work_out_status(manual, approval.approved_on if approval else None, rating, bool(rating), lines, complete,
                             submitted=submitted)
    # During a periodic review the next review date stays the one set by the last approval
    last = approved_snapshots(case_id, folder)
    if approval and decision:
        next_review = next_review_date(approval.approved_on, decision.rating).isoformat()
    elif last:
        next_review = next_review_date(last[0].approved_on, last[0].risk.get("rating", "")).isoformat()
    else:
        next_review = ""
    return AssessmentSummary(
        case_id, cycle_review_id(case_id, cycle), draft["entity_name"] or "Unnamed entity", draft.get("company_link", ""),
        INDUSTRIES.get(industry_key, ""), CHECKLISTS[checklist_key][0] if checklist_key in CHECKLISTS else "",
        rating, validated, lines, status, approval.approver if approval else "",
        draft["saved_at"].replace("T", " ")[:16], manual.reason if manual else "", next_review, cycle,
        bool(lines) and complete >= lines, owner_of(draft), last_activity(draft), draft["review_id"],
    )


def last_activity(draft: dict) -> str:
    """When anyone last worked on the assessment: its newest audit log entry, or when it was last saved."""
    events = load_events(case_file(draft["id"], "audit").with_suffix(".jsonl"))
    saved = draft["saved_at"].replace("T", " ")
    return max([saved] + [e.at for e in events])[:16]


UNASSIGNED = "Unassigned"


def owner_of(draft: dict) -> str:
    """The assessment's owner: who created it, unless it was reassigned. For assessments saved before owners were
    recorded, the name on the audit log's creation entry, if there is one."""
    if draft.get("owner"):
        return draft["owner"]
    created = next((e for e in load_events(case_file(draft["id"], "audit").with_suffix(".jsonl"))
                    if e.what.startswith("Created the assessment")), None)
    return created.who if created and created.who not in ("", NO_NAME) else UNASSIGNED


def all_assessments(folder: Path | None = None) -> list[AssessmentSummary]:
    """Every saved assessment (one per legal entity), most recently saved first."""
    return [summarise(draft, folder) for draft in latest_reviews(folder)]


def earlier_approved_reviews(folder: Path | None = None) -> list[AssessmentSummary]:
    """Approved reviews that a periodic review has since followed: one row each, with its own ID, status Approved
    and the risk rating, checklist and next review date it was approved with."""
    rows = []
    for current in all_assessments(folder):
        for snapshot in approved_snapshots(current.case_id, folder):
            if snapshot.cycle == current.cycle:
                continue  # the current review already has its row
            rating = snapshot.risk.get("rating", "")
            reviewed = [line for line in snapshot.lines if line.section.startswith(REVIEWED_BEFORE_APPROVAL)]
            rows.append(replace(
                current, review_id=cycle_review_id(current.case_id, snapshot.cycle), status=APPROVED, risk=rating,
                industry=INDUSTRIES.get(snapshot.industry, current.industry),
                checklist=CHECKLISTS[snapshot.checklist][0] if snapshot.checklist in CHECKLISTS else current.checklist,
                validated=len(reviewed), lines=len(reviewed), approved_by=snapshot.approved_by, status_reason="",
                next_review=next_review_date(snapshot.approved_on, rating).isoformat(), cycle=snapshot.cycle,
                ready=False, last_activity=snapshot.approved_on, followed_by=current.review_id))
    return rows


# --- Recent activity across every assessment, from their audit logs ---

DOCUMENT_UPLOAD, AI_PROCESSING, CREATION, ANALYST_ACTION = (
    "Document upload", "AI processing", "Assessment creation", "Analyst action")


@dataclass(frozen=True)
class Activity:
    at: str  # YYYY-MM-DD HH:MM:SS
    who: str
    kind: str
    what: str
    line: str
    entity_name: str
    review_id: str
    case_id: str


def activity_kind(who: str, what: str) -> str:
    """Sort an audit log entry into the dashboard's kinds of activity."""
    if what.startswith("Created the assessment"):
        return CREATION
    if who in ("Claude", "Clario", "Clario AI"):
        return AI_PROCESSING
    if what.startswith(("Uploaded document", "Added supporting document", "Deleted document", "Removed document")):
        return DOCUMENT_UPLOAD
    return ANALYST_ACTION


def recent_activity(limit: int = 15, folder: Path | None = None) -> list[Activity]:
    """The latest audit log entries across every assessment, newest first."""
    activity = []
    for draft in latest_reviews(folder):
        path = case_file(draft["id"], "audit").with_suffix(".jsonl")
        for event in load_events(path):
            activity.append(Activity(event.at, event.who, activity_kind(event.who, event.what), event.what,
                                     event.line, draft["entity_name"] or "Unnamed entity", draft["review_id"],
                                     draft["id"]))
    return sorted(activity, key=lambda a: a.at, reverse=True)[:limit]
