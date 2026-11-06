"""Review cycles: onboarding is cycle 1, each periodic review is the next cycle.

Each cycle has its own line reviews, risk decision, submission and approval. At approval the whole checklist is
frozen into a snapshot, so anyone can see exactly what was present at that point. A periodic review runs the
checklist again as at the date it started, so evidence that has gone out of date is flagged, and every line starts
without a Validated tick, so the analyst checks each one again before it is submitted for approval. Files live in the
review's folder in the git-ignored cases folder.
"""

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

from services.cases import CASES_DIR, review_id
from services.checklist import Check
from services.pack import CheckOutcome, PackAssessment, UploadedDocument
from services.validator import Status


def _folder(case_id: str, folder: Path | None) -> Path:
    return (folder or CASES_DIR) / case_id


def current_cycle(case_id: str, folder: Path | None = None) -> int:
    path = _folder(case_id, folder) / "cycle.json"
    return json.loads(path.read_text())["cycle"] if path.exists() else 1


def cycle_key(case_id: str, cycle: int) -> str:
    """The key the cycle's review files are saved under. Cycle 1 keeps the review's own id."""
    return case_id if cycle == 1 else f"{case_id}-cycle-{cycle}"


def cycle_review_id(case_id: str, cycle: int) -> str:
    """Each review cycle's own ID, linked to the original: CLR-9580685D, then CLR-9580685D-PR1 for periodic review 1."""
    original = review_id(case_id)
    return original if cycle == 1 else f"{original}-PR{cycle - 1}"


def start_periodic_review(case_id: str, folder: Path | None = None, today: date | None = None) -> int:
    """Begin the next review cycle. Returns its number."""
    cycle = current_cycle(case_id, folder) + 1
    path = _folder(case_id, folder)
    path.mkdir(parents=True, exist_ok=True)
    (path / "cycle.json").write_text(json.dumps({"cycle": cycle,
                                                  "started_on": (today or date.today()).isoformat()}, indent=2))
    return cycle


def cycle_started_on(case_id: str, folder: Path | None = None) -> date | None:
    """The date the current periodic review started; None during onboarding."""
    path = _folder(case_id, folder) / "cycle.json"
    return date.fromisoformat(json.loads(path.read_text())["started_on"]) if path.exists() else None


def assessment_answer_path(case_id: str, cycle: int, folder: Path | None = None) -> Path:
    """Where a periodic review keeps Claude's answer for its checklist run, so reopening it costs nothing."""
    return _folder(case_id, folder) / f"assessment-cycle-{cycle}.answer.json"


# --- Submission for approval ---

def submission_path(case_id: str, cycle: int, folder: Path | None = None) -> Path:
    return _folder(case_id, folder) / f"submitted-cycle-{cycle}.json"


def submit_for_approval(case_id: str, cycle: int, by: str, outstanding: list[str], folder: Path | None = None,
                        today: date | None = None) -> None:
    """The analyst hands the review to the approver. Only when every line is Present and validated."""
    if outstanding:
        raise ValueError(f"Cannot submit: {len(outstanding)} line(s) are not complete ({', '.join(outstanding)})")
    if not by.strip():
        raise ValueError("Give your name")
    path = submission_path(case_id, cycle, folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"by": by.strip(), "on": (today or date.today()).isoformat()}, indent=2))


def load_submission(case_id: str, cycle: int, folder: Path | None = None) -> dict | None:
    path = submission_path(case_id, cycle, folder)
    return json.loads(path.read_text()) if path.exists() else None


def withdraw_submission(case_id: str, cycle: int, folder: Path | None = None) -> None:
    submission_path(case_id, cycle, folder).unlink(missing_ok=True)


# --- Snapshots frozen at approval ---

@dataclass(frozen=True)
class FrozenLine:
    id: str
    section: str
    check: str
    evidence_source: str
    evidence_type: str
    status: str
    finding: str
    evidence: list[str] = field(default_factory=list)
    decided_by: str = ""
    claude_finding: str = ""
    before_review: str = ""
    validated_by: str = ""
    comment: str = ""


@dataclass(frozen=True)
class Snapshot:
    cycle: int
    approved_by: str
    approved_on: str
    note: str
    industry: str
    checklist: str
    risk: dict  # the risk decision as saved
    documents: list[dict]  # name, description, kind ("original" or "supporting for 3.6")
    lines: list[FrozenLine]
    frozen_at: str = ""

    def as_assessment(self) -> PackAssessment:
        """The frozen checklist as results, e.g. to show it read-only."""
        return PackAssessment([CheckOutcome(
            Check(line.id, line.section, line.check, line.evidence_source, line.evidence_type),
            Status(line.status), line.finding, list(line.evidence), line.decided_by, line.claude_finding,
            line.before_review, line.validated_by, line.comment) for line in self.lines])


def snapshot_path(case_id: str, cycle: int, folder: Path | None = None) -> Path:
    return _folder(case_id, folder) / f"approved-cycle-{cycle}.json"


def snapshot_documents_dir(case_id: str, cycle: int, folder: Path | None = None) -> Path:
    """Where the documents used at approval are kept: copies that later uploads or deletions never touch."""
    return _folder(case_id, folder) / f"approved-cycle-{cycle}-documents"


def keep_documents(case_id: str, cycle: int, documents: list[dict], files: dict[str, UploadedDocument],
                   folder: Path | None = None) -> list[dict]:
    """Keep a copy of each document (matched by name) with the approved record. Returns the document records with
    each copy's sha256 and media type."""
    store = snapshot_documents_dir(case_id, cycle, folder)
    store.mkdir(parents=True, exist_ok=True)
    kept = []
    for document in documents:
        file = files.get(document["name"])
        if file and not document.get("sha256"):
            (store / file.fingerprint).write_bytes(file.data)
            document = {**document, "sha256": file.fingerprint, "media_type": file.media_type}
        kept.append(document)
    return kept


def approved_document(case_id: str, cycle: int, sha256: str, folder: Path | None = None) -> bytes | None:
    """A document as it was at approval, or None if no copy was kept."""
    path = snapshot_documents_dir(case_id, cycle, folder) / sha256
    return path.read_bytes() if sha256 and path.exists() else None


def attach_documents(case_id: str, cycle: int, files: dict[str, UploadedDocument],
                     folder: Path | None = None) -> Snapshot | None:
    """For a record approved before documents were kept: keep copies of the ones still on file (matched by name)."""
    snapshot = load_snapshot(case_id, cycle, folder)
    if not snapshot or all(d.get("sha256") for d in snapshot.documents):
        return snapshot
    path = snapshot_path(case_id, cycle, folder)
    record = json.loads(path.read_text())
    record["documents"] = keep_documents(case_id, cycle, record["documents"], files, folder)
    path.write_text(json.dumps(record, indent=2))
    return load_snapshot(case_id, cycle, folder)


def freeze(case_id: str, cycle: int, assessment: PackAssessment, approved_by: str, approved_on: str, note: str,
           industry: str, checklist: str, risk: dict, documents: list[dict], folder: Path | None = None,
           files: dict[str, UploadedDocument] | None = None) -> Snapshot:
    """Freeze the checklist as it stands at approval, with a copy of each document used (files, by name)."""
    documents = keep_documents(case_id, cycle, documents, files or {}, folder)
    lines = [FrozenLine(o.check.id, o.check.section, o.check.check, o.check.evidence_source, o.check.evidence_type,
                        o.status.value, o.finding, list(o.evidence), o.decided_by, o.claude_finding, o.before_review,
                        o.validated_by, o.reviewer_note) for o in assessment.outcomes]
    snapshot = Snapshot(cycle, approved_by, approved_on, note, industry, checklist, risk, documents, lines,
                        datetime.now().isoformat(timespec="seconds"))
    path = snapshot_path(case_id, cycle, folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(snapshot), indent=2))
    return snapshot


def load_snapshot(case_id: str, cycle: int, folder: Path | None = None) -> Snapshot | None:
    path = snapshot_path(case_id, cycle, folder)
    if not path.exists():
        return None
    record = json.loads(path.read_text())
    record["lines"] = [FrozenLine(**line) for line in record["lines"]]
    return Snapshot(**record)


def remove_snapshot(case_id: str, cycle: int, folder: Path | None = None) -> None:
    """Used when an approval is withdrawn: the checklist is no longer frozen, and its kept documents go too."""
    snapshot_path(case_id, cycle, folder).unlink(missing_ok=True)
    shutil.rmtree(snapshot_documents_dir(case_id, cycle, folder), ignore_errors=True)


def approved_snapshots(case_id: str, folder: Path | None = None) -> list[Snapshot]:
    """Every approved cycle, most recent first."""
    found = [load_snapshot(case_id, cycle, folder) for cycle in range(1, current_cycle(case_id, folder) + 1)]
    return [s for s in reversed(found) if s]


def copy_file(source: Path, destination: Path) -> None:
    """Used to start a periodic review with the last cycle's risk decision, which the analyst can then change."""
    if source.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source.read_text())

