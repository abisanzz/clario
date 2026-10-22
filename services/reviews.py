"""An analyst's changes to check results, saved on this computer so they are still there next time.

Each case (one set of documents checked against one checklist) has its own file in the reviews folder.
The folder is git-ignored: analysts' notes on real cases must not be committed.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path

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

    def __post_init__(self):
        if not self.note.strip():
            raise ValueError("Give a reason for the change")
        if not self.reviewer.strip():
            raise ValueError("Give the reviewer's name")


def case_file(pack_key: str, checklist: str, folder: Path | None = None) -> Path:
    """Where one case's changes are saved: one file per set of documents and checklist."""
    name = hashlib.sha256(f"{pack_key}|{checklist}".encode()).hexdigest()[:16]
    return (folder or REVIEWS_DIR) / f"{name}.json"


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
    path.parent.mkdir(exist_ok=True)
    data = {
        check_id: {**asdict(o), "status": o.status.value, "original_status": o.original_status.value}
        for check_id, o in overrides.items()
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2))
    temporary.replace(path)  # write in one go, so a half-written file is never left behind


def save_override(path: Path, assessment: PackAssessment, check_id: str, status: Status, note: str,
                  reviewer: str, today: date | None = None) -> Override:
    """Record the analyst's answer for one check, keeping the original answer beside it."""
    original = next(o for o in assessment.outcomes if o.check.id == check_id)
    override = Override(check_id, status, note.strip(), reviewer.strip(), (today or date.today()).isoformat(),
                        original.status, original.finding, original.decided_by)
    overrides = load_overrides(path)
    overrides[check_id] = override
    _write(path, overrides)
    return override


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
            outcome = replace(
                outcome,
                status=override.status,
                finding=override.note,
                decided_by=f"Analyst: {override.reviewer}, {override.reviewed_on}",
                before_review=f"{outcome.status.value} ({outcome.decided_by}): {outcome.finding}",
            )
        outcomes.append(outcome)
    return replace(assessment, outcomes=outcomes)
