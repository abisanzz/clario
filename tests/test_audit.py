from datetime import datetime

from services.audit import NO_NAME, describe_line_change, events_csv, load_events, log_event


def test_entries_are_added_and_shown_newest_first(tmp_path):
    path = tmp_path / "audit.jsonl"
    assert load_events(path) == []
    log_event(path, "A. Analyst", "Status Unclear → Present", "3.2", when=datetime(2026, 10, 31, 9, 15, 2))
    log_event(path, "B. Head", "Approved the review", when=datetime(2026, 10, 31, 16, 0, 0))
    events = load_events(path)
    assert [(e.at, e.who, e.line, e.what) for e in events] == [
        ("2026-10-31 16:00:00", "B. Head", "", "Approved the review"),
        ("2026-10-31 09:15:02", "A. Analyst", "3.2", "Status Unclear → Present"),
    ]


def test_the_log_is_only_ever_added_to(tmp_path):
    path = tmp_path / "audit.jsonl"
    log_event(path, "A. Analyst", "first")
    first = path.read_text()
    log_event(path, "B. Reviewer", "second")
    assert path.read_text().startswith(first)


def test_a_missing_name_is_recorded_as_such(tmp_path):
    path = tmp_path / "audit.jsonl"
    assert log_event(path, "  ", "Validated").who == NO_NAME


def test_line_changes_are_described_in_plain_english():
    assert describe_line_change("Unclear", "Present", False, True, "", "Client confirmed 25%") == (
        'Status Unclear → Present; ticked Validated; comment "Client confirmed 25%"')
    assert describe_line_change("Missing", "Missing", True, False, "old", "") == "unticked Validated; removed the comment"


def test_the_log_downloads_as_csv(tmp_path):
    path = tmp_path / "audit.jsonl"
    log_event(path, "A. Analyst", 'Added "wealth.pdf"', "3.6", when=datetime(2026, 10, 31, 9, 0, 0))
    assert events_csv(load_events(path)).splitlines() == [
        "Time,Who,Line,What", '2026-10-31 09:00:00,A. Analyst,3.6,"Added ""wealth.pdf"""']
