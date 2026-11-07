"""An append-only audit log for each review: who changed what, and when.

Entries are only ever added, one JSON line each, in a file kept with the review on this computer (git-ignored).
"""

import csv
import io
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

NO_NAME = "Name not given"


@dataclass(frozen=True)
class AuditEvent:
    at: str  # YYYY-MM-DD HH:MM:SS
    who: str
    line: str  # a check ID, a section, or "" for the whole review
    what: str


def log_event(path: Path, who: str, what: str, line: str = "", when: datetime | None = None) -> AuditEvent:
    """Add one entry to the review's audit log."""
    event = AuditEvent((when or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"), who.strip() or NO_NAME, line, what)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as log:
        log.write(json.dumps(asdict(event)) + "\n")
    return event


def load_events(path: Path) -> list[AuditEvent]:
    """Every entry, newest first."""
    if not path.exists():
        return []
    events = [AuditEvent(**json.loads(line)) for line in path.read_text().splitlines() if line.strip()]
    return list(reversed(events))


def events_csv(events: list[AuditEvent]) -> str:
    """The log as a spreadsheet-friendly CSV file."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Time", "Who", "Line", "What"])
    writer.writerows([[e.at, e.who, e.line, e.what] for e in events])
    return out.getvalue()


def describe_line_change(before_status: str, after_status: str, before_validated: bool, after_validated: bool,
                         before_comment: str, after_comment: str) -> str:
    """A plain-English summary of what changed on a checklist line."""
    parts = []
    if before_status != after_status:
        parts.append(f"Status {before_status} → {after_status}")
    if before_validated != after_validated:
        parts.append("ticked Validated" if after_validated else "unticked Validated")
    if before_comment.strip() != after_comment.strip():
        parts.append(f'comment "{after_comment.strip()}"' if after_comment.strip() else "removed the comment")
    return "; ".join(parts) or "Saved with no change"
