"""Read meeting-note files into Notes, or explain why a file must be skipped."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import yaml

from .models import ActionTrackError, Note

HEADER_SCAN_LINES = 15
TITLE_RE = re.compile(r"^#\s*Meeting\s*:\s*(.*?)\s*$", re.IGNORECASE)
DATE_RE = re.compile(r"^Date\s*:\s*(.*?)\s*$", re.IGNORECASE)
ATTENDEES_RE = re.compile(r"^Attendees\s*:\s*(.*?)\s*$", re.IGNORECASE)
FILENAME_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
ORDINAL_RE = re.compile(r"(\d)(st|nd|rd|th)\b", re.IGNORECASE)
DATE_FORMATS = (
    "%Y-%m-%d",
    "%d %B %Y",
    "%d %b %Y",
    "%A, %d %B %Y",
    "%A %d %B %Y",
    "%a, %d %b %Y",
    "%a %d %b %Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%B %d %Y",
)


class SkipNote(Exception):
    """Raised when a file is not a usable meeting note; the message is the reason."""


@dataclass
class ScanResult:
    notes: list[Note] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    ignored: list[tuple[str, str]] = field(default_factory=list)


def parse_header_date(value) -> date | None:
    """Parse a meeting date written in any of the supported header formats."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = re.sub(r"\s+", " ", ORDINAL_RE.sub(r"\1", str(value).strip()))
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def split_attendees(value) -> list[str]:
    if value is None:
        return []
    parts = [str(v) for v in value] if isinstance(value, (list, tuple)) else re.split(r"[,;]", str(value))
    return [re.sub(r"\s+", " ", p).strip() for p in parts if p and p.strip()]


def read_note(path: Path) -> Note:
    data = path.read_bytes()
    if not data.strip():
        raise SkipNote("empty file")
    if b"\x00" in data:
        raise SkipNote("not valid UTF-8 text (binary content)")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise SkipNote("not valid UTF-8 text") from None
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    title = raw_date = raw_attendees = None
    body_start = 0
    if lines[0].strip() == "---":
        title, raw_date, raw_attendees, body_start = _frontmatter(lines)
    plain_title, plain_date, plain_attendees = _plain_header(lines, body_start)
    title = title if title is not None else plain_title
    raw_date = raw_date if raw_date is not None else plain_date
    raw_attendees = raw_attendees if raw_attendees is not None else plain_attendees

    if title is None and raw_date is None and raw_attendees is None:
        raise SkipNote("no meeting header (no title, Date or Attendees line)")

    warnings: list[str] = []
    if raw_date is None:
        match = FILENAME_DATE_RE.match(path.name)
        meeting_date = parse_header_date(match.group(1)) if match else None
        if meeting_date is None:
            raise SkipNote("no meeting date (no Date line and no date in the file name)")
        warnings.append("no Date line; using the date from the file name")
    else:
        meeting_date = parse_header_date(raw_date)
        if meeting_date is None:
            raise SkipNote(f"unparseable date '{raw_date}'")

    attendees = split_attendees(raw_attendees)
    if not attendees:
        warnings.append("no Attendees line; owners resolved against the people roster")

    return Note(
        path=path,
        title=str(title).strip() if title else path.stem,
        meeting_date=meeting_date,
        attendees=attendees,
        lines=lines,
        body_start=body_start,
        warnings=warnings,
    )


def _frontmatter(lines: list[str]):
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise SkipNote("frontmatter is not closed with '---'")
    try:
        meta = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError:
        raise SkipNote("frontmatter is not valid YAML") from None
    if not isinstance(meta, dict):
        raise SkipNote("frontmatter is not a key/value block")
    meta = {str(k).lower(): v for k, v in meta.items()}
    title = meta.get("title")
    return (str(title) if title else None), meta.get("date"), meta.get("attendees"), end + 1


def _plain_header(lines: list[str], start: int):
    title = raw_date = raw_attendees = None
    for line in lines[start:start + HEADER_SCAN_LINES]:
        line = line.strip()
        if title is None and (m := TITLE_RE.match(line)):
            title = m.group(1)
        elif raw_date is None and (m := DATE_RE.match(line)):
            raw_date = m.group(1)
        elif raw_attendees is None and (m := ATTENDEES_RE.match(line)):
            raw_attendees = m.group(1)
    return title, raw_date, raw_attendees


def scan_folder(folder: Path) -> ScanResult:
    """Read every .md file in `folder` (not subfolders). One bad file never stops the scan."""
    if not folder.exists():
        raise ActionTrackError(f"folder not found: {folder}")
    if not folder.is_dir():
        raise ActionTrackError(f"not a folder: {folder}")
    result = ScanResult()
    for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if path.is_dir():
            result.ignored.append((path.name + "/", "subfolder (not scanned)"))
            continue
        if path.suffix.lower() != ".md":
            result.ignored.append((path.name, "not a .md file"))
            continue
        try:
            result.notes.append(read_note(path))
        except SkipNote as exc:
            result.skipped.append((path.name, str(exc)))
        except Exception as exc:  # noqa: BLE001 - a bad file must never stop the run
            result.skipped.append((path.name, f"parser error: {type(exc).__name__}"))
    return result
