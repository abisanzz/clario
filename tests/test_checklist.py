import pytest
from openpyxl import Workbook

from services.checklist import Check, load_checks

HEADINGS = ["ID", "Section", "Check", "Evidence source", "Evidence type", "Status"]
EVIDENCE_TYPES = {"Client document", "Client questionnaire", "Public register", "Screening tool", "Internal decision"}


def make_workbook(path, rows, headings=HEADINGS):
    """Save a small practice checklist spreadsheet for a test."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Checklist"
    sheet.append(headings)
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    return path


def test_section_1_has_checks_1_1_to_1_4():
    ids = [c.id for c in load_checks() if c.section == "1. Legal existence"]
    assert ids == ["1.1", "1.2", "1.3", "1.4"]


def test_check_1_1_is_read_correctly():
    check = next(c for c in load_checks() if c.id == "1.1")
    assert check == Check(
        id="1.1",
        section="1. Legal existence",
        check="Registered name, company number, incorporation date and legal form",
        evidence_source="Certificate of incorporation; Companies House",
        evidence_type="Client document",
    )


def test_ids_are_unique():
    ids = [c.id for c in load_checks()]
    assert len(ids) == len(set(ids))


def test_every_check_has_text_and_a_known_evidence_type():
    for check in load_checks():
        assert check.check, f"{check.id} has no check text"
        assert check.evidence_type in EVIDENCE_TYPES, f"{check.id} has unknown evidence type"


def test_blank_rows_are_skipped(tmp_path):
    path = make_workbook(tmp_path / "checklist.xlsx", [
        ["1.1", "1. Legal existence", "First", "Doc", "Client document"],
        [None, None, None, None, None],
        ["1.2", "1. Legal existence", "Second", "Doc", "Client document"],
    ])
    assert [c.id for c in load_checks(path)] == ["1.1", "1.2"]


def test_missing_column_gives_clear_error(tmp_path):
    path = make_workbook(tmp_path / "checklist.xlsx", [], headings=["ID", "Section", "Check"])
    with pytest.raises(ValueError, match="Evidence source, Evidence type"):
        load_checks(path)
