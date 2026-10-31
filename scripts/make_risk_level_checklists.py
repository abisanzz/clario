"""Draft Low and High risk versions of every industry checklist. The existing checklists are the Medium versions.

Low = simplified due diligence: lighter identity, purpose-only business checks, no source of funds or senior approval,
review every 3 years. High = enhanced due diligence: the Medium checks plus source of wealth, extra independent
verification, documented source of funds, enhanced adverse media, recorded EDD measures and closer monitoring.
Check IDs stay the same as in the Medium version; added checks take the next free number in their section.

Drafted by Claude from general knowledge of UK rules and reviewed on 31 Oct 2026 (see REVIEWED_ON). Any change to
the content below needs a fresh review.
Run from the project folder (overwrites the drafts):  .venv/bin/python scripts/make_risk_level_checklists.py
"""

import sys
from copy import copy
from pathlib import Path

import openpyxl
from openpyxl.styles import Font

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from services.checklist import BASE_CHECKLISTS  # noqa: E402

DRAFTED_ON = "31 Oct 2026"
REVIEWED_ON = "31 Oct 2026"
UNCHECKED = f"Reviewed, {REVIEWED_ON}"
CLIENT_DOC, SCREENING, INTERNAL = "Client document", "Screening tool", "Internal decision"

LEVELS = {
    "Low": {
        "label": "simplified due diligence, for a client rated low risk",
        "replace": {
            "4.2": ("Identity verified for beneficial owners and for the directors or signatories acting on the account, "
                    "using one reliable source each (an identity document or electronic verification)", None, None),
            "5.2": ("Purpose and intended nature of the relationship", None, None),
            "8.1": ("Review date set: every 3 years for a low-risk client", None, None),
        },
        "remove": {"5.3": "Source of funds", "7.3": "Senior management approval"},
        "add": {},
        "figures": [("Simplified due diligence", "Allowed where the business relationship presents a low risk of money "
                     "laundering, taking the risk assessment into account. Customer and beneficial owner identification "
                     "is still required.", "All", "Money Laundering Regulations 2017, regulation 37")],
    },
    "High": {
        "label": "enhanced due diligence, for a client rated high risk",
        "replace": {
            "4.2": ("Identity verified for beneficial owners and for the directors or signatories acting on the account, "
                    "using at least two independent sources (for example a certified document and electronic "
                    "verification)", None, None),
            "5.3": ("Source of funds supported by documentary evidence (for example investment agreements, bank "
                    "statements or audited accounts)", "Supporting documents", CLIENT_DOC),
            "8.1": ("Review date set: every year for a high-risk client", None, None),
        },
        "remove": {},
        "add": {
            "3.": [("Source of wealth of each beneficial owner established and supported by evidence",
                    "Source of wealth declaration; supporting evidence", CLIENT_DOC)],
            "5.": [("Expected activity checked against independent information (latest accounts, website, public "
                    "sources)", "Annual accounts; company website; public sources", CLIENT_DOC)],
            "6.": [("Enhanced adverse media and open-source search on the entity, owners and directors, with the "
                    "results documented", "Screening tool / open-source search", SCREENING)],
            "7.": [("Reasons for the high risk rating and the enhanced due diligence measures applied are recorded",
                    "Case file; risk assessment", INTERNAL)],
            "8.": [("Enhanced ongoing monitoring: closer transaction monitoring and earlier review triggers",
                    "Monitoring set-up", INTERNAL)],
        },
        "figures": [("Enhanced due diligence", "Required where there is a high risk of money laundering, including "
                     "PEPs and high-risk third countries; includes more scrutiny of source of wealth and funds and "
                     "senior management approval.", "All", "Money Laundering Regulations 2017, regulations 33 to 35")],
    },
}


def level_path(medium: Path, level: str) -> Path:
    return medium.with_name(medium.stem + f"_{level}.xlsx")


def rows_for(level: dict, medium_rows: list[list]) -> list[list]:
    """The Medium checklist's rows, changed for this level."""
    ids = {row[0] for row in medium_rows}
    for check_id in list(level["replace"]) + list(level["remove"]):
        assert check_id in ids, f"check {check_id} is missing from the Medium checklist"
    rows = []
    for row in medium_rows:
        check_id = row[0]
        if check_id in level["remove"]:
            assert level["remove"][check_id].split()[0].lower() in row[2].lower(), (check_id, row[2])
            continue
        if check_id in level["replace"]:
            text, source, kind = level["replace"][check_id]
            row = [check_id, row[1], text, source or row[3], kind or row[4]]
        rows.append(row)
    # added checks go at the end of their section, numbered after the section's last Medium check
    result = []
    for index, row in enumerate(rows):
        result.append(row)
        prefix = row[0].split(".")[0] + "."
        last_in_section = index == len(rows) - 1 or not rows[index + 1][0].startswith(prefix)
        if last_in_section and prefix in level["add"]:
            numbers = [int(r[0].split(".")[1]) for r in medium_rows if r[0].startswith(prefix)]
            for offset, (text, source, kind) in enumerate(level["add"][prefix], start=1):
                result.append([f"{prefix}{max(numbers) + offset}", row[1], text, source, kind])
    return result


def copy_style(sheet, from_row: int, to_row: int, columns: int):
    for column in range(1, columns + 1):
        sheet.cell(to_row, column)._style = copy(sheet.cell(from_row, column)._style)
    sheet.row_dimensions[to_row].height = sheet.row_dimensions[from_row].height


def build(medium: Path, level_name: str) -> Path:
    level = LEVELS[level_name]
    workbook = openpyxl.load_workbook(medium)
    sheet = workbook["Checklist"]
    medium_rows = [[c.value for c in row[:5]] for row in sheet.iter_rows(min_row=2, max_row=sheet.max_row)
                   if row[0].value]
    rows = rows_for(level, medium_rows)

    last_row = len(medium_rows) + 1
    for number in range(2, max(len(rows), len(medium_rows)) + 2):
        row = rows[number - 2] if number - 2 < len(rows) else None
        copy_style(sheet, last_row if row else last_row + 1, number, 10)
        for column in range(1, 11):
            sheet.cell(number, column).value = None
        if row:
            for column, value in enumerate(row, start=1):
                sheet.cell(number, column).value = value
            sheet.cell(number, 6).value = "Not started"
    sheet.auto_filter.ref = f"A1:J{len(rows) + 1}"

    figures = workbook["Key figures"]
    start = figures.max_row + 1
    for offset, (figure, meaning, used_in, source) in enumerate(level["figures"]):
        copy_style(figures, start - 1, start + offset, 5)
        for column, value in enumerate((figure, meaning, used_in, source, UNCHECKED), start=1):
            figures.cell(start + offset, column).value = value

    guide = workbook["Guide"]
    guide["A2"] = (f"{level_name} risk version ({level['label']}), drafted by Claude on {DRAFTED_ON} from the "
                   f"approved Medium checklist and reviewed on {REVIEWED_ON}. Recheck dates and thresholds when the "
                   "regulations change.")
    guide["A2"].font = Font(i=True, sz=11)
    note_row = guide.max_row + 1
    copy_style(guide, note_row - 1, note_row, 2)
    removed = ", ".join(f"{k} ({v})" for k, v in level["remove"].items())
    guide.cell(note_row, 1).value = "-"
    guide.cell(note_row, 2).value = (
        f"{level_name} risk version: checks {', '.join(level['replace'])} are reworded"
        + (f"; {removed} removed" if removed else "")
        + ("; extra enhanced due diligence checks added at the end of sections "
           + ", ".join(p.rstrip('.') for p in level["add"]) if level["add"] else "")
        + ". Check IDs otherwise match the Medium version.")

    path = level_path(medium, level_name)
    workbook.save(path)
    return path


if __name__ == "__main__":
    for key, (name, medium) in BASE_CHECKLISTS.items():
        for level_name in LEVELS:
            print("Built", build(medium, level_name).name)
