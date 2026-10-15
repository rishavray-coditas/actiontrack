from datetime import date

import pytest

from actiontrack import reader
from actiontrack.models import ActionTrackError
from actiontrack.reader import SkipNote, read_note, scan_folder

from .conftest import SAMPLE


def test_standard_header():
    note = read_note(SAMPLE / "2026-09-01-quote-portal-kickoff.md")
    assert note.meeting_date == date(2026, 9, 1)
    assert note.attendees == ["Priya Nair", "Rahul Mehta", "Anita Desai", "Sam Okafor"]
    assert note.title == "Quote portal kickoff"
    assert note.warnings == []


def test_title_with_colon():
    note = read_note(SAMPLE / "2026-09-21-incident-review.md")
    assert note.title == "Incident review: billing double-charge"


def test_yaml_frontmatter():
    note = read_note(SAMPLE / "2026-09-16-standup.md")
    assert note.meeting_date == date(2026, 9, 16)
    assert note.attendees == ["Anita Desai", "Lena Fischer", "Meera Iyer"]
    assert note.title == "Team standup"
    assert note.body_start > 0


@pytest.mark.parametrize("name, expected", [
    ("2026-09-09-qa-standup.md", date(2026, 9, 9)),               # "9 September 2026"
    ("2026-09-14-onboarding-flow-design.md", date(2026, 9, 14)),  # "Monday, 14 September 2026"
])
def test_long_form_dates(name, expected):
    assert read_note(SAMPLE / name).meeting_date == expected


@pytest.mark.parametrize("name, reason", [
    ("2026-09-09-notes-final-v2.md", "empty file"),
    ("scratch.md", "not valid UTF-8 text"),
    ("untitled.md", "no meeting header"),
    ("2026-10-03-sales-pipeline.md", "unparseable date 'sometime last week'"),
])
def test_malformed_notes_are_skipped(name, reason):
    with pytest.raises(SkipNote) as exc:
        read_note(SAMPLE / name)
    assert reason in str(exc.value)


def test_missing_attendees_is_a_warning_not_a_skip():
    note = read_note(SAMPLE / "2026-09-23-standup.md")
    assert note.attendees == []
    assert any("no Attendees line" in w for w in note.warnings)


def test_missing_date_falls_back_to_filename(tmp_path):
    path = tmp_path / "2026-10-21-standup.md"
    path.write_text("# Meeting: Standup\nAttendees: Neha Rao\n\n- [ ] Neha to update the dashboard\n")
    note = read_note(path)
    assert note.meeting_date == date(2026, 10, 21)
    assert any("file name" in w for w in note.warnings)


def test_missing_date_without_filename_date_is_skipped(tmp_path):
    path = tmp_path / "no-date.md"
    path.write_text("# Meeting: Standup\nAttendees: Neha Rao\n\n- [ ] Neha to send the invoice by Friday\n")
    with pytest.raises(SkipNote, match="no meeting date"):
        read_note(path)


def test_invalid_utf8_is_skipped(tmp_path):
    path = tmp_path / "000_broken.md"
    path.write_bytes(b"# Meeting: x\nDate: \xc3\x28\n")
    with pytest.raises(SkipNote, match="UTF-8"):
        read_note(path)


def test_crlf_and_bom_read_like_lf(tmp_path):
    original = (SAMPLE / "2026-09-01-quote-portal-kickoff.md").read_text(encoding="utf-8")
    path = tmp_path / "2026-09-01-copy.md"
    path.write_bytes(b"\xef\xbb\xbf" + original.replace("\n", "\r\n").encode("utf-8"))
    a, b = read_note(SAMPLE / "2026-09-01-quote-portal-kickoff.md"), read_note(path)
    assert (a.meeting_date, a.attendees, a.lines) == (b.meeting_date, b.attendees, b.lines)


def test_scan_folder_reports_everything():
    result = scan_folder(SAMPLE)
    assert len(result.notes) == 31
    assert {name for name, _ in result.skipped} == {
        "2026-09-09-notes-final-v2.md", "2026-10-03-sales-pipeline.md", "scratch.md", "untitled.md"}
    assert result.ignored == [("2026-09-19-offsite-draft.txt", "not a .md file")]


def test_unexpected_error_in_one_file_does_not_stop_scan(tmp_path, monkeypatch):
    for name in ("000_bad.md", "2026-10-01-good.md"):
        (tmp_path / name).write_text("# Meeting: x\nDate: 2026-10-01\nAttendees: A B\n")
    real = reader.read_note

    def flaky(path):
        if path.name == "000_bad.md":
            raise RuntimeError("boom")
        return real(path)

    monkeypatch.setattr(reader, "read_note", flaky)
    result = scan_folder(tmp_path)
    assert result.skipped == [("000_bad.md", "parser error: RuntimeError")]
    assert [n.name for n in result.notes] == ["2026-10-01-good.md"]


def test_missing_folder_is_a_clear_error(tmp_path):
    with pytest.raises(ActionTrackError, match="folder not found"):
        scan_folder(tmp_path / "nope")
