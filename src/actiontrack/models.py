"""Data types shared across actiontrack modules."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path


class ActionTrackError(Exception):
    """An expected, user-facing error. The CLI prints it without a traceback."""


@dataclass
class Note:
    """A meeting note that passed the reader's checks."""

    path: Path
    title: str
    meeting_date: date
    attendees: list[str]
    lines: list[str]
    body_start: int  # index of the first line after any YAML frontmatter
    warnings: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.name


@dataclass
class RawItem:
    """One action-item line as found in a note, before owner/date resolution."""

    file: str
    line: int
    text: str
    checked: bool
    kind: str  # "checkbox" | "action" | "table"


@dataclass
class Mention:
    """One appearance of an item in one meeting note."""

    file: str
    line: int
    meeting_date: str  # ISO date
    meeting_title: str
    checked: bool
    raw: str
    task: str
    due: str | None  # ISO date
    due_raw: str | None
    due_status: str  # "resolved" | "none" | "unresolved"


@dataclass
class Item:
    """A tracked action item: one or more mentions merged together."""

    id: int
    task: str
    owner_status: str  # "resolved" | "ambiguous" | "unassigned" | "unknown"
    owners: list[str]
    owner_raw: str | None
    owner_label: str | None
    candidates: list[str]
    due: str | None
    due_raw: str | None
    due_status: str
    status: str  # "open" | "done"
    done_by: str | None  # "note" | "manual"
    done_at: str | None
    first_seen: str
    mentions: list[Mention] = field(default_factory=list)

    @property
    def due_date(self) -> date | None:
        return date.fromisoformat(self.due) if self.due else None

    @property
    def latest(self) -> Mention:
        return self.mentions[-1]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Item":
        data = dict(data)
        data["mentions"] = [Mention(**m) for m in data.get("mentions", [])]
        return cls(**data)


@dataclass
class IngestReport:
    scanned: int = 0
    ingested: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    ignored: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[tuple[str, str]] = field(default_factory=list)
    new_items: list[int] = field(default_factory=list)
    updated_items: set[int] = field(default_factory=set)
    merged_mentions: int = 0
    known_mentions: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.new_items or self.updated_items or self.merged_mentions)
