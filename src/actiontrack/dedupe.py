"""Merge repeated action items into one tracked item.

Two mentions are the same item when they have the same owner key and
near-identical task text (token-set Jaccard >= 0.8 after normalising).
The latest mention sets the wording and done state; the latest mention that
states a due date sets the due date. A manual `done` is never undone.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .dates import DueResult
from .models import Item, Mention
from .owners import OwnerResult
from .store import Store

SIMILARITY_THRESHOLD = 0.8
STOPWORDS = {"the", "a", "an", "to", "for", "of", "with", "their", "its", "our"}


@dataclass
class Candidate:
    owner: OwnerResult
    due: DueResult
    mention: Mention


def tokens(text: str) -> frozenset[str]:
    text = text.lower().replace("’", "'")
    text = re.sub(r"'s\b", "", text)
    return frozenset(w for w in re.findall(r"[a-z0-9]+", text) if w not in STOPWORDS)


def similarity(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def owner_key(status: str, owners: list[str], candidates: list[str], raw: str | None) -> tuple:
    if status == "resolved":
        return ("resolved", tuple(sorted(owners)))
    if status == "unassigned":
        return ("unassigned",)
    return (status, tuple(sorted(owners)), tuple(sorted(candidates)), (raw or "").lower())


def item_key(item: Item) -> tuple:
    return owner_key(item.owner_status, item.owners, item.candidates, item.owner_raw)


def candidate_key(cand: Candidate) -> tuple:
    o = cand.owner
    return owner_key(o.status, o.owners, o.candidates, o.raw)


def merge(store: Store, cand: Candidate) -> tuple[str, Item]:
    """Add a candidate to the store. Returns ("known" | "merged" | "new", item)."""
    m = cand.mention
    for item in store.items:
        if any(x.file == m.file and x.line == m.line and x.raw == m.raw for x in item.mentions):
            return "known", item

    key = candidate_key(cand)
    wanted = tokens(m.task)
    best, best_score = None, 0.0
    for item in store.items:
        if item_key(item) != key:
            continue
        score = max(similarity(tokens(x.task), wanted) for x in item.mentions)
        if score >= SIMILARITY_THRESHOLD and score > best_score:
            best, best_score = item, score
    if best:
        best.mentions.append(m)
        refresh(best)
        return "merged", best

    o = cand.owner
    item = store.add(Item(
        id=0, task=m.task, owner_status=o.status, owners=list(o.owners), owner_raw=o.raw,
        owner_label=o.label, candidates=list(o.candidates), due=None, due_raw=None,
        due_status="none", status="open", done_by=None, done_at=None,
        first_seen=m.meeting_date, mentions=[m],
    ))
    refresh(item)
    return "new", item


def refresh(item: Item) -> None:
    """Recompute an item's derived fields from its mentions."""
    item.mentions.sort(key=lambda x: (x.meeting_date, x.file, x.line))
    latest = item.mentions[-1]
    item.task = latest.task
    item.first_seen = item.mentions[0].meeting_date
    with_due = [x for x in item.mentions if x.due_status != "none"]
    if with_due:
        d = with_due[-1]
        item.due, item.due_raw, item.due_status = d.due, d.due_raw, d.due_status
    else:
        item.due, item.due_raw, item.due_status = None, None, "none"
    if item.done_by == "manual":
        return
    if latest.checked:
        item.status, item.done_by, item.done_at = "done", "note", latest.meeting_date
    else:
        item.status, item.done_by, item.done_at = "open", None, None
