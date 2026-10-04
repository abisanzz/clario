import pytest
from openpyxl import load_workbook

from services.checklist import CHECKLIST_PATH
from services.validator import CheckResult, Status


def statuses_in_guide():
    """Read the status names listed under 'Status | Meaning' on the Guide tab."""
    workbook = load_workbook(CHECKLIST_PATH, read_only=True)
    try:
        names, collecting = [], False
        for row in workbook["Guide"].iter_rows(min_col=1, max_col=2, values_only=True):
            if row[0] == "Status" and row[1] == "Meaning":
                collecting = True
            elif collecting and row[0]:
                names.append(row[0])
            elif collecting:
                break
        return names
    finally:
        workbook.close()


def test_statuses_match_the_spreadsheet_guide():
    assert [s.value for s in Status] == statuses_in_guide()


def test_misspelled_status_is_rejected():
    with pytest.raises(ValueError):
        Status("Presnt")


def test_result_keeps_its_details():
    result = CheckResult("1.1", Status.PRESENT, "All four details found", "Certificate of incorporation p.1")
    assert result.check_id == "1.1"
    assert result.status is Status.PRESENT
    assert result.finding == "All four details found"
    assert result.source_reference == "Certificate of incorporation p.1"


def test_not_started_needs_no_finding():
    assert CheckResult("1.1", Status.NOT_STARTED).finding == ""


@pytest.mark.parametrize("status", [s for s in Status if s is not Status.NOT_STARTED])
def test_other_statuses_require_a_finding(status):
    with pytest.raises(ValueError, match="must include a finding"):
        CheckResult("1.1", status, "   ")


def test_status_must_be_a_status_not_plain_text():
    with pytest.raises(TypeError):
        CheckResult("1.1", "Present", "Looks fine")
