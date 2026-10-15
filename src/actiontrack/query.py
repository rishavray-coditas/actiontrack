"""Filtering, overdue logic and person lookup for `list` and `followup`."""
from __future__ import annotations

from datetime import date

from .models import ActionTrackError, Item
from .owners import match_names

STATUSES = ("open", "done", "overdue")
SPECIAL_OWNERS = ("unassigned", "ambiguous", "unknown")


class PersonNotFound(ActionTrackError):
    pass


def is_overdue(item: Item, today: date) -> bool:
    """Not done and due strictly before today. An item due today is not overdue."""
    due = item.due_date
    return item.status != "done" and due is not None and due < today


def days_overdue(item: Item, today: date) -> int:
    return (today - item.due_date).days if is_overdue(item, today) else 0


def known_people(items: list[Item], people: list[str]) -> list[str]:
    names = list(people)
    for item in items:
        names.extend(item.owners)
        names.extend(item.candidates)
    return list(dict.fromkeys(names))


def resolve_person(query: str, names: list[str]) -> str:
    matches = match_names(query, names)
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise PersonNotFound(f"no one called '{query}' is in the item store or people.yaml")
    raise ActionTrackError(
        f"'{query}' matches more than one person: {', '.join(sorted(matches))}. Use the full name."
    )


def filter_items(
    items: list[Item],
    *,
    today: date,
    owner: str | None = None,
    status: str | None = None,
    due_before: date | None = None,
    people: list[str] = (),
) -> list[Item]:
    """Apply all filters (combined with AND) and sort the result."""
    selected = list(items)
    if owner:
        key = owner.strip().lower()
        if key in SPECIAL_OWNERS:
            selected = [i for i in selected if i.owner_status == key]
        else:
            person = resolve_person(owner, known_people(items, list(people)))
            selected = [i for i in selected if person in i.owners]
    if status == "open":
        selected = [i for i in selected if i.status != "done"]
    elif status == "done":
        selected = [i for i in selected if i.status == "done"]
    elif status == "overdue":
        selected = [i for i in selected if is_overdue(i, today)]
    if due_before:
        selected = [i for i in selected if i.due_date and i.due_date < due_before]
    return sort_items(selected, today)


def sort_items(items: list[Item], today: date) -> list[Item]:
    """Overdue first, then other open items by due date (undated last), then done items."""
    def key(item: Item):
        group = 0 if is_overdue(item, today) else 1 if item.status != "done" else 2
        return (group, item.due or "9999-12-31", item.id)
    return sorted(items, key=key)
