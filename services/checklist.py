"""Load the KYC checklist spreadsheet into Python objects."""

from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

DOCS = Path(__file__).resolve().parent.parent / "docs"
CHECKLIST_PATH = DOCS / "UK_Fintech_KYC_Checklist.xlsx"

# The checklists a user can choose from: key -> (name shown to the user, spreadsheet)
CHECKLISTS = {
    "fintech": ("Fintech: payments and e-money", CHECKLIST_PATH),
    "general": ("General business (not financial services)", DOCS / "UK_General_Business_KYC_Checklist.xlsx"),
    "crypto": ("Crypto", DOCS / "UK_Crypto_KYC_Checklist.xlsx"),
    "lending": ("Lending and credit", DOCS / "UK_Lending_KYC_Checklist.xlsx"),
    "investment_firm": ("Investment firm", DOCS / "UK_Investment_Firm_KYC_Checklist.xlsx"),
    "asset_management": ("Asset management", DOCS / "UK_Asset_Management_KYC_Checklist.xlsx"),
}
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
