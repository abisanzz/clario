"""An analyst's changes to check results, saved on this computer so they are still there next time.

Each case (one set of documents checked against one checklist) has its own file in the reviews folder.
The folder is git-ignored: analysts' notes on real cases must not be committed.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path

from services.demo import visitor_space
from services.pack import PackAssessment
from services.validator import Status

REVIEWS_DIR = Path(__file__).resolve().parent.parent / "reviews"


@dataclass(frozen=True)
class Override:
    """The analyst's answer for one check, and what Claude or the rules said before."""

    check_id: str
    status: Status
    note: str
    reviewer: str
    reviewed_on: str  # YYYY-MM-DD
    original_status: Status
    original_finding: str
    original_decided_by: str
    validated: bool = False  # the analyst has checked this line
    via: str = ""  # set when Claude changed the line from a supporting document: that document's name

    def __post_init__(self):
        if self.status is not self.original_status and not self.note.strip():
            raise ValueError("Add a comment explaining the change")
        if not self.reviewer.strip():
            raise ValueError("Give the reviewer's name")


def case_file(pack_key: str, checklist: str, folder: Path | None = None) -> Path:
    """Where one case's changes are saved: one file per set of documents and checklist."""
    name = hashlib.sha256(f"{pack_key}|{checklist}".encode()).hexdigest()[:16]
    return (folder or visitor_space(REVIEWS_DIR)) / f"{name}.json"


def load_overrides(path: Path) -> dict[str, Override]:
    """The analyst's changes for a case, by check ID (none if nothing has been saved)."""
    if not path.exists():
        return {}
    saved = json.loads(path.read_text())
    return {
        check_id: Override(**{**item, "status": Status(item["status"]),
                              "original_status": Status(item["original_status"])})
        for check_id, item in saved.items()
    }


def _write(path: Path, overrides: dict[str, Override]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        check_id: {**asdict(o), "status": o.status.value, "original_status": o.original_status.value}
        for check_id, o in overrides.items()
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2))
    temporary.replace(path)  # write in one go, so a half-written file is never left behind


def save_override(path: Path, assessment: PackAssessment, check_id: str, status: Status, note: str,
                  reviewer: str, today: date | None = None, validated: bool = False, via: str = "") -> Override:
    """Record the analyst's answer for one check, keeping the original answer beside it."""
    original = next(o for o in assessment.outcomes if o.check.id == check_id)
    override = Override(check_id, status, note.strip(), reviewer.strip(), (today or date.today()).isoformat(),
                        original.status, original.finding, original.decided_by, validated, via)
    overrides = load_overrides(path)
    overrides[check_id] = override
    _write(path, overrides)
    return override


def save_line_reviews(path: Path, assessment: PackAssessment, lines: list[tuple[str, Status, str, bool]],
                      reviewer: str, today: date | None = None) -> list[str]:
    """Save the reviewer's line-by-line review: (check id, status, note, validated) for each line they touched.

    Every line is checked first; if any is incomplete nothing is saved and the problems are returned.
    A line set back to the original status, with no note and not validated, has its earlier review removed.
    """
    originals = {o.check.id: o for o in assessment.outcomes}
    problems = []
    if lines and not reviewer.strip():
        problems.append("Give the reviewer's name")
    for check_id, status, note, _ in lines:
        if status is not originals[check_id].status and not note.strip():
            problems.append(f"{check_id}: add a comment explaining why you changed the status to {status.value}")
    if problems:
        return problems
    for check_id, status, note, validated in lines:
        if status is originals[check_id].status and not note.strip() and not validated:
            remove_override(path, check_id)
        else:
            save_override(path, assessment, check_id, status, note, reviewer, today, validated)
    return []


def remove_override(path: Path, check_id: str) -> None:
    """Undo the analyst's change, so the original answer shows again."""
    overrides = load_overrides(path)
    if overrides.pop(check_id, None) is not None:
        _write(path, overrides)


def apply_overrides(assessment: PackAssessment, overrides: dict[str, Override]) -> PackAssessment:
    """The results with the analyst's answers in place; counts and gap lists follow them."""
    outcomes = []
    for outcome in assessment.outcomes:
        override = overrides.get(outcome.check.id)
        if override:
            who = f"{override.reviewer}, {override.reviewed_on}"
            changes = {"reviewer_note": override.note, "validated_by": who if override.validated else ""}
            if override.status is not outcome.status:
                changes.update(
                    status=override.status,
                    finding=override.note,
                    decided_by=(f"Clario AI, from supporting document {override.via}, {override.reviewed_on}"
                                if override.via else f"Analyst: {who}"),
                    before_review=f"{outcome.status.value} ({outcome.decided_by}): {outcome.finding}",
                )
            outcome = replace(outcome, **changes)
        outcomes.append(outcome)
    return replace(assessment, outcomes=outcomes)


# --- Final approval: senior management signs off every review at the end ---

@dataclass(frozen=True)
class FinalApproval:
    approver: str
    approved_on: str  # YYYY-MM-DD
    note: str = ""


def outstanding_lines(assessment: PackAssessment) -> list[str]:
    """Lines that stop approval: every line must be Present and validated. E.g. "3.1 Missing", "5.3 not validated"."""
    problems = []
    for o in assessment.outcomes:
        if o.status is not Status.PRESENT:
            problems.append(f"{o.check.id} {o.status.value}")
        elif not o.validated_by:
            problems.append(f"{o.check.id} not validated")
    return problems


def approve_review(path: Path, approver: str, note: str = "", today: date | None = None,
                   outstanding: list[str] = ()) -> FinalApproval:
    """Record senior management's approval of the whole review. Refused while any line is outstanding."""
    if outstanding:
        raise ValueError(f"Cannot approve: {len(outstanding)} line(s) are not complete ({', '.join(outstanding)})")
    if not approver.strip():
        raise ValueError("Give the senior manager's name")
    approval = FinalApproval(approver.strip(), (today or date.today()).isoformat(), note.strip())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(approval), indent=2))
    return approval


def load_approval(path: Path) -> FinalApproval | None:
    return FinalApproval(**json.loads(path.read_text())) if path.exists() else None


def withdraw_approval(path: Path) -> None:
    path.unlink(missing_ok=True)
