"""Split an item into owner + task and resolve the owner to a full name.

Owners are resolved against the meeting's own attendees first, then against
the global roster (people.yaml plus every attendee seen). A first name shared
by two candidates is never guessed: the item is marked ambiguous.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

HANDLE_RE = re.compile(r"^@(?P<handle>[A-Za-z][\w.-]*)\s*:?\s+(?P<task>.+)$")
OWNER_TO_RE = re.compile(r"^(?P<owner>\S.*?)\s+to\s+(?P<task>.+)$")
HELPER_RE = re.compile(r"\(\s*with\s+(?P<helper>[^)]+?)\s*\)", re.IGNORECASE)
NAME_SPLIT_RE = re.compile(r"\s*(?:&|\+|/|,|\band\b)\s*")
NAME_TOKEN_RE = re.compile(r"^[A-Z][\w'’-]*\.?$")
JOINERS = {"&", "and", "+", "/"}
MAX_OWNER_TOKENS = 5

PLACEHOLDERS = {"someone", "somebody", "anyone", "anybody", "tbd", "tba", "owner", "nobody", "unknown"}
GROUPS = {"everyone", "everybody", "all", "team", "the team", "we", "us", "all of us"}


@dataclass
class OwnerResult:
    task: str
    status: str  # "resolved" | "ambiguous" | "unassigned" | "unknown"
    owners: list[str] = field(default_factory=list)
    raw: str | None = None
    label: str | None = None
    candidates: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def split_owner(text: str) -> tuple[str | None, str]:
    """Return (owner phrase, task). The owner phrase is None when there is none."""
    if m := HANDLE_RE.match(text):
        return m.group("handle"), m.group("task")
    m = OWNER_TO_RE.match(text)
    if m and _looks_like_owner(m.group("owner")):
        return m.group("owner"), m.group("task")
    return None, text


def _looks_like_owner(phrase: str) -> bool:
    bare = HELPER_RE.sub("", phrase).strip()
    if not bare:
        return False
    if bare.lower() in PLACEHOLDERS | GROUPS:
        return True
    tokens = bare.split()
    if len(tokens) > MAX_OWNER_TOKENS:
        return False
    return all(t.lower() in JOINERS or NAME_TOKEN_RE.match(t.rstrip(",")) for t in tokens)


def match_names(name: str, people: list[str]) -> list[str]:
    """Match a written name ('Priya', 'Priya N.', 'priya nair', '@anita') to full names."""
    wanted = re.sub(r"\s+", " ", name.strip().lstrip("@").rstrip(":")).lower()
    if not wanted:
        return []
    exact = [p for p in people if p.lower() == wanted]
    if exact:
        return list(dict.fromkeys(exact))
    tokens = [t for t in wanted.replace(".", " ").split() if t]
    first, rest = tokens[0], tokens[1:]
    found = []
    for person in people:
        parts = person.lower().split()
        if not parts or parts[0] != first:
            continue
        if rest and not (len(parts) > 1 and parts[-1].startswith(rest[0])):
            continue
        found.append(person)
    return list(dict.fromkeys(found))


def resolve_owner(text: str, attendees: list[str], roster: list[str]) -> OwnerResult:
    phrase, task = split_owner(text)
    if phrase is None:
        return OwnerResult(task=text, status="unassigned")

    helper = None
    if m := HELPER_RE.search(phrase):
        helper = m.group("helper")
        phrase = HELPER_RE.sub("", phrase).strip()

    key = phrase.lower()
    if key in PLACEHOLDERS:
        return OwnerResult(task=task, status="unassigned", raw=phrase, label=phrase)
    if key in GROUPS:
        return OwnerResult(task=task, status="unassigned", raw=phrase, label=phrase)

    owners: list[str] = []
    candidates: list[str] = []
    unknown: list[str] = []
    warnings: list[str] = []
    for name in filter(None, NAME_SPLIT_RE.split(phrase)):
        matches, source = _lookup(name, attendees, roster)
        if len(matches) == 1:
            owners.append(matches[0])
            if source == "roster" and attendees:
                warnings.append(f"'{name}' is not in the attendee list; matched {matches[0]} from the roster")
        elif matches:
            candidates.extend(matches)
        else:
            unknown.append(name)

    if helper:
        helper_matches, _ = _lookup(helper, attendees, roster)
        task = f"{task} (with {helper_matches[0] if len(helper_matches) == 1 else helper})"

    status = "ambiguous" if candidates else "unknown" if unknown else "resolved"
    return OwnerResult(
        task=task,
        status=status,
        owners=list(dict.fromkeys(owners)),
        raw=phrase,
        candidates=sorted(set(candidates)),
        warnings=warnings,
    )


def _lookup(name: str, attendees: list[str], roster: list[str]) -> tuple[list[str], str]:
    found = match_names(name, attendees)
    if found:
        return found, "attendees"
    return match_names(name, roster), "roster"
