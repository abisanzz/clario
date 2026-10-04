"""Load the KYC checklist spreadsheet into Python objects."""

from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

CHECKLIST_PATH = Path(__file__).resolve().parent.parent / "docs" / "UK_Fintech_KYC_Checklist.xlsx"
SHEET_NAME = "Checklist"

# Spreadsheet heading -> field name on Check
COLUMNS = {
    "ID": "id",
    "Section": "section",
    "Check": "check",
    "Evidence source": "evidence_source",
    "Evidence type": "evidence_type",
}


@dataclass(frozen=True)
class Check:
    id: str
    section: str
    check: str
    evidence_source: str
    evidence_type: str


def load_checks(path: Path = CHECKLIST_PATH) -> list[Check]:
    """Return every check on the Checklist tab, in spreadsheet order."""
    workbook = load_workbook(path, read_only=True)
    try:
        rows = workbook[SHEET_NAME].iter_rows(values_only=True)
        headings = [str(h).strip() if h is not None else "" for h in next(rows)]

        missing = [name for name in COLUMNS if name not in headings]
        if missing:
            raise ValueError(f"Checklist is missing columns: {', '.join(missing)}")
        positions = {field: headings.index(name) for name, field in COLUMNS.items()}

        checks = []
        for row in rows:
            values = {field: row[i] for field, i in positions.items()}
            if values["id"] is None or str(values["id"]).strip() == "":
                continue
            checks.append(Check(**{f: str(v).strip() if v is not None else "" for f, v in values.items()}))
        return checks
    finally:
        workbook.close()
