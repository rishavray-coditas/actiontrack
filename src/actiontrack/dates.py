"""Resolve due phrases ("by Friday", "end of month", "Oct 3rd") to real dates.

Everything is relative to the meeting date, never to today. Only phrases
introduced by a deadline word (by, due, on, before, until) count; "from 9 Oct"
or "for November" describe when something happens, not a deadline.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tues": 1, "tue": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thurs": 3, "thur": 3, "thu": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}
MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
# A date in "10 Sep" form more than this many days before the meeting is taken to be next year.
YEAR_ROLLOVER_DAYS = 183


def _alternation(names) -> str:
    return "|".join(sorted(names, key=len, reverse=True))


WD = f"(?:{_alternation(WEEKDAYS)})"
MON = f"(?:{_alternation(MONTHS)})"
ORD = r"(?:st|nd|rd|th)?"

DATE_EXPR = "|".join([
    r"\d{4}-\d{2}-\d{2}",
    rf"(?:{WD},?\s+)?\d{{1,2}}{ORD}\s+(?:of\s+)?{MON}\.?(?:,?\s+\d{{4}})?",
    rf"(?:{WD},?\s+)?{MON}\.?\s+\d{{1,2}}{ORD}(?:,?\s+\d{{4}})?",
    r"(?:eod|cob|end\s+of\s+(?:the\s+)?day)\s+tomorrow",
    r"(?:the\s+)?end\s+of\s+(?:the\s+)?next\s+week",
    r"(?:the\s+)?end\s+of\s+(?:the\s+|this\s+)?week|eow",
    r"(?:the\s+)?end\s+of\s+(?:the\s+|this\s+)?month|eom",
    rf"(?:the\s+)?end\s+of\s+{MON}",
    rf"mid[-\s]{MON}",
    rf"next\s+{WD}",
    r"next\s+week",
    r"tomorrow|today|tonight|eod|cob|end\s+of\s+(?:the\s+)?day",
    WD,
])
INTRO = r"(?:by|until|till|before|on|no\s+later\s+than|(?:results?\s+)?due(?:\s+(?:by|on))?)"
END = r"(?![\w'’-])"
DUE_RE = re.compile(rf"(?<![\w-])(?P<intro>{INTRO})\s+(?P<expr>{DATE_EXPR}){END}", re.IGNORECASE)
BARE_RE = re.compile(r"(?<![\w-])(?P<expr>(?:eod\s+)?tomorrow|today|tonight|eod)\s*[.!]?\s*$", re.IGNORECASE)
VAGUE_RE = re.compile(
    r"(?<![\w-])(?P<phrase>(?:before|until)\s+[^,;]+?"
    r"|by\s+(?:the\s+)?(?:next|end|start|beginning|early|late|mid|close)\b[^,;]*?)\s*[.!]?\s*$",
    re.IGNORECASE,
)
TRAILING_SEPARATORS_RE = re.compile(r"[\s,;:—–-]+$")


@dataclass
class DueResult:
    task: str  # the task with the due clause removed
    due: date | None
    raw: str | None  # the due phrase as written
    status: str  # "resolved" | "none" | "unresolved"


def resolve_due(text: str, anchor: date) -> DueResult:
    """Find the last due clause in `text` and resolve it against the meeting date."""
    matches = list(DUE_RE.finditer(text))
    if matches:
        m = matches[-1]
        due = resolve_expression(m.group("expr"), anchor)
        task = _tidy(text[:m.start()] + " " + text[m.end():])
        return DueResult(task, due, _squash(m.group(0)), "resolved" if due else "unresolved")
    if m := BARE_RE.search(text):
        due = resolve_expression(m.group("expr"), anchor)
        return DueResult(_tidy(text[:m.start()]), due, _squash(m.group("expr")), "resolved" if due else "unresolved")
    if m := VAGUE_RE.search(text):
        return DueResult(_tidy(text), None, _squash(m.group("phrase")), "unresolved")
    return DueResult(_tidy(text), None, None, "none")


def resolve_expression(expr: str, anchor: date) -> date | None:
    e = _squash(expr).lower()
    e = re.sub(r"^the ", "", e)

    if m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", e):
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if m := re.fullmatch(rf"(?:{WD},? )?(\d{{1,2}}){ORD} (?:of )?({MON})\.?(?:,? (\d{{4}}))?", e):
        return _day_month(int(m.group(1)), MONTHS[m.group(2)], m.group(3), anchor)
    if m := re.fullmatch(rf"(?:{WD},? )?({MON})\.? (\d{{1,2}}){ORD}(?:,? (\d{{4}}))?", e):
        return _day_month(int(m.group(2)), MONTHS[m.group(1)], m.group(3), anchor)
    if re.fullmatch(r"(?:(?:eod|cob|end of (?:the )?day) )?tomorrow", e):
        return anchor + timedelta(days=1)
    if re.fullmatch(r"today|tonight|eod|cob|end of (?:the )?day", e):
        return anchor
    monday = anchor - timedelta(days=anchor.weekday())
    if re.fullmatch(r"end of (?:the )?next week|next week", e):
        return monday + timedelta(days=7 + 4)
    if re.fullmatch(r"end of (?:the |this )?week|eow", e):
        friday = monday + timedelta(days=4)
        return friday if anchor.weekday() <= 4 else friday + timedelta(days=7)
    if re.fullmatch(r"end of (?:the |this )?month|eom", e):
        return _last_day(anchor.year, anchor.month)
    if m := re.fullmatch(rf"end of ({MON})", e):
        first = _day_month(1, MONTHS[m.group(1)], None, anchor)
        return _last_day(first.year, first.month) if first else None
    if m := re.fullmatch(rf"mid[- ]({MON})", e):
        return _day_month(15, MONTHS[m.group(1)], None, anchor)
    if m := re.fullmatch(rf"next ({WD})", e):
        return monday + timedelta(days=7 + WEEKDAYS[m.group(1)])
    if e in WEEKDAYS:
        # Next occurrence strictly after the meeting: "by Friday" said on a Friday means next week.
        days = (WEEKDAYS[e] - anchor.weekday()) % 7 or 7
        return anchor + timedelta(days=days)
    return None


def _day_month(day: int, month: int, year: str | None, anchor: date) -> date | None:
    if year:
        return _safe_date(int(year), month, day)
    candidate = _safe_date(anchor.year, month, day)
    if candidate and candidate < anchor - timedelta(days=YEAR_ROLLOVER_DAYS):
        candidate = _safe_date(anchor.year + 1, month, day)
    return candidate


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _last_day(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _tidy(text: str) -> str:
    text = _squash(text)
    text = TRAILING_SEPARATORS_RE.sub("", text).rstrip(".")
    return text.strip()
