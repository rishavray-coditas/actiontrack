"""Find action-item lines in a note's body.

Recognised: checkbox bullets (`-`, `*`, `+`, any indent, `[ ]`/`[x]`/`[X]`),
`ACTION:` lines, and rows of a markdown table whose header has an Action/Task
column. Ignored: blockquotes, fenced code blocks, HTML comments and prose.
"""
from __future__ import annotations

import re

from .models import Note, RawItem

CHECKBOX_RE = re.compile(r"^\s*[-*+]\s+\[(?P<mark>[ xX])\]\s+(?P<text>.+?)\s*$")
ACTION_RE = re.compile(r"^\s*ACTION\s*:\s*(?P<text>.+?)\s*$", re.IGNORECASE)
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
TABLE_ROW_RE = re.compile(r"^\s*\|(?P<cells>.*)\|\s*$")
TABLE_SEPARATOR_RE = re.compile(r"^[\s|:\-]+$")
INLINE_COMMENT_RE = re.compile(r"<!--.*?-->")
EMPTY_CELLS = {"", "-", "—", "n/a", "na", "tbd"}

OWNER_COLUMNS = ("owner", "who", "assignee")
ACTION_COLUMNS = ("action", "action item", "task", "what")
DUE_COLUMNS = ("due", "due date", "deadline", "when", "by")


def extract_items(note: Note) -> list[RawItem]:
    items: list[RawItem] = []
    fence: str | None = None
    in_comment = False
    table: dict | None = None  # None = not in a table; {} = table without an action column

    for index in range(note.body_start, len(note.lines)):
        line = note.lines[index]
        if fence:
            if line.strip().startswith(fence):
                fence = None
            continue
        if in_comment:
            if "-->" not in line:
                continue
            line = line.split("-->", 1)[1]
            in_comment = False
        line = INLINE_COMMENT_RE.sub("", line)
        if "<!--" in line:
            line = line.split("<!--", 1)[0]
            in_comment = True

        if m := FENCE_RE.match(line):
            fence = m.group(1)[:3]
            table = None
            continue
        stripped = line.strip()
        if not stripped:
            table = None
            continue
        if stripped.startswith(">"):
            continue

        if row := TABLE_ROW_RE.match(line):
            cells = [c.strip() for c in row.group("cells").split("|")]
            if table is None:
                table = _table_columns(cells)
            elif table and not TABLE_SEPARATOR_RE.match(stripped):
                text = _table_item(cells, table)
                if text:
                    items.append(RawItem(note.name, index + 1, text, False, "table"))
            continue
        table = None

        if m := CHECKBOX_RE.match(line):
            items.append(RawItem(note.name, index + 1, m.group("text"), m.group("mark") in "xX", "checkbox"))
        elif m := ACTION_RE.match(line):
            items.append(RawItem(note.name, index + 1, m.group("text"), False, "action"))
    return items


def _table_columns(cells: list[str]) -> dict:
    lowered = [c.lower() for c in cells]

    def find(names):
        return next((i for i, c in enumerate(lowered) if c in names), None)

    action = find(ACTION_COLUMNS)
    if action is None:
        return {}
    return {"owner": find(OWNER_COLUMNS), "action": action, "due": find(DUE_COLUMNS)}


def _table_item(cells: list[str], columns: dict) -> str | None:
    def cell(key):
        i = columns.get(key)
        return cells[i].strip() if i is not None and i < len(cells) else ""

    action = cell("action")
    if action.lower() in EMPTY_CELLS:
        return None
    owner, due = cell("owner"), cell("due")
    if owner.lower() not in EMPTY_CELLS:
        if action[:1].isupper() and action[1:2].islower():
            action = action[0].lower() + action[1:]
        text = f"{owner} to {action}"
    else:
        text = action
    if due.lower() not in EMPTY_CELLS:
        text += f" by {due}"
    return text
