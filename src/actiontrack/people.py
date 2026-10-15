"""Load the people directory (people.yaml): full names and email addresses."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .models import ActionTrackError

PEOPLE_ENV = "ACTIONTRACK_PEOPLE"


@dataclass
class People:
    path: Path | None
    emails: dict[str, str] = field(default_factory=dict)

    @property
    def names(self) -> list[str]:
        return list(self.emails)


def find_people_file(explicit: Path | None, store_dir: Path) -> tuple[Path | None, bool]:
    """Return (path, required). An explicitly named file must exist; defaults are optional."""
    if explicit:
        return explicit, True
    if env := os.environ.get(PEOPLE_ENV):
        return Path(env), True
    for candidate in (Path.cwd() / "people.yaml", store_dir / "people.yaml"):
        if candidate.is_file():
            return candidate, False
    return None, False


def load_people(explicit: Path | None, store_dir: Path) -> People:
    path, required = find_people_file(explicit, store_dir)
    if path is None:
        return People(None)
    if not path.is_file():
        if required:
            raise ActionTrackError(f"people file not found: {path}")
        return People(None)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ActionTrackError(f"could not read people file {path}: {exc}") from None
    return People(path, _parse(data, path))


def _parse(data, path: Path) -> dict[str, str]:
    """Accept either `people: [{name, email}, ...]` or a plain `Name: email` mapping."""
    emails: dict[str, str] = {}
    entries = data.get("people", data) if isinstance(data, dict) else data
    if isinstance(entries, dict):
        for name, email in entries.items():
            emails[str(name).strip()] = str(email or "").strip()
    elif isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("name"):
                raise ActionTrackError(f"people file {path}: every entry needs a 'name'")
            emails[str(entry["name"]).strip()] = str(entry.get("email") or "").strip()
    else:
        raise ActionTrackError(f"people file {path}: expected a 'people' list")
    return emails
