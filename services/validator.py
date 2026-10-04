"""Decide a status for each KYC checklist item."""

from dataclasses import dataclass
from enum import Enum


class Status(Enum):
    """The five statuses used on the checklist spreadsheet, spelled exactly the same."""

    NOT_STARTED = "Not started"
    PRESENT = "Present"
    MISSING = "Missing"
    UNCLEAR = "Unclear"
    NEEDS_HUMAN_REVIEW = "Needs human review"


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one check, mirroring the spreadsheet's Status, Finding and Source reference columns."""

    check_id: str
    status: Status
    finding: str = ""
    source_reference: str = ""

    def __post_init__(self):
        if not isinstance(self.status, Status):
            raise TypeError(f"{self.check_id}: status must be a Status, not {self.status!r}")
        if self.status is not Status.NOT_STARTED and not self.finding.strip():
            raise ValueError(f"{self.check_id}: a '{self.status.value}' result must include a finding")
