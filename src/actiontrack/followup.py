"""Compose one follow-up email per owner: overdue items first, then open ones."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from .models import Item
from .query import is_overdue, sort_items


@dataclass
class Draft:
    owner: str
    to: str
    subject: str
    body: str
    item_ids: list[int]

    def to_dict(self) -> dict:
        return asdict(self)


def items_for(items: list[Item], person: str) -> list[Item]:
    """Open items this person definitely owns. Ambiguous and unassigned items never qualify."""
    return [i for i in items if i.status != "done" and person in i.owners]


def compose_followup(person: str, email: str, items: list[Item], today: date) -> Draft:
    items = sort_items(items, today)
    overdue = [i for i in items if is_overdue(i, today)]
    upcoming = [i for i in items if not is_overdue(i, today) and i.due]
    undated = [i for i in items if not i.due]

    first_name = person.split()[0]
    lines = [
        f"Hi {first_name},",
        "",
        "Here is a quick follow-up on the action items from our recent meetings "
        f"that are still open as of {_fmt(today)}.",
    ]
    number = 0
    for heading, group in (("OVERDUE", overdue), ("COMING UP", upcoming), ("NO DUE DATE YET", undated)):
        if not group:
            continue
        lines += ["", heading]
        for item in group:
            number += 1
            lines.append(f"{number}. {_sentence(item.task)} [#{item.id}]")
            lines.append(f"   {_due_text(item, today)}; from {_source(item)}")
    lines += [
        "",
        "If any of these are already done, or need a new date, just reply and let me know.",
        "",
        "Thanks!",
    ]
    subject = (
        f"Action items follow-up: {len(items)} open ({len(overdue)} overdue) – as of {today.isoformat()}"
    )
    return Draft(owner=person, to=email, subject=subject, body="\n".join(lines) + "\n",
                 item_ids=[i.id for i in items])


def _due_text(item: Item, today: date) -> str:
    if item.due_date:
        if is_overdue(item, today):
            days = (today - item.due_date).days
            return f"was due {_fmt(item.due_date)} ({days} day{'s' if days != 1 else ''} overdue)"
        return f"due {_fmt(item.due_date)}"
    if item.due_raw:
        return f"due: {item.due_raw}"
    return "no due date"


def _source(item: Item) -> str:
    latest = item.latest
    return f"\"{latest.meeting_title}\" on {_fmt(date.fromisoformat(latest.meeting_date))}"


def _sentence(task: str) -> str:
    return task[:1].upper() + task[1:]


def _fmt(d: date) -> str:
    return f"{d:%a} {d.day} {d:%b %Y}"
