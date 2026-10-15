"""`ingest`: read a folder of notes and merge their action items into the store."""
from __future__ import annotations

from pathlib import Path

from .dates import resolve_due
from .dedupe import Candidate, merge
from .extractor import extract_items
from .models import IngestReport, Mention, Note
from .owners import resolve_owner
from .reader import scan_folder
from .store import Store


def build_candidates(note: Note, roster: list[str]) -> list[Candidate]:
    candidates = []
    for raw in extract_items(note):
        owner = resolve_owner(raw.text, note.attendees, roster)
        due = resolve_due(owner.task, note.meeting_date)
        owner.task = due.task
        mention = Mention(
            file=raw.file,
            line=raw.line,
            meeting_date=note.meeting_date.isoformat(),
            meeting_title=note.title,
            checked=raw.checked,
            raw=raw.text,
            task=due.task,
            due=due.due.isoformat() if due.due else None,
            due_raw=due.raw,
            due_status=due.status,
        )
        candidates.append(Candidate(owner=owner, due=due, mention=mention))
    return candidates


def ingest_folder(folder: Path, store: Store, people: list[str]) -> IngestReport:
    scan = scan_folder(folder)
    report = IngestReport(
        scanned=len(scan.notes) + len(scan.skipped) + len(scan.ignored),
        skipped=list(scan.skipped),
        ignored=list(scan.ignored),
    )
    attendees = sorted({a for note in scan.notes for a in note.attendees})
    stored_owners = [o for item in store.items for o in item.owners]
    roster = list(dict.fromkeys([*people, *attendees, *stored_owners]))
    existing_ids = {item.id for item in store.items}

    for note in sorted(scan.notes, key=lambda n: (n.meeting_date, n.name.lower())):
        try:
            candidates = build_candidates(note, roster)
        except Exception as exc:  # noqa: BLE001 - a bad note must never stop the run
            report.skipped.append((note.name, f"parser error: {type(exc).__name__}"))
            continue
        report.ingested.append(note.name)
        report.warnings.extend((note.name, w) for w in note.warnings)
        for cand in candidates:
            report.warnings.extend((note.name, f"line {cand.mention.line}: {w}") for w in cand.owner.warnings)
            outcome, item = merge(store, cand)
            if outcome == "known":
                report.known_mentions += 1
            elif outcome == "new":
                report.new_items.append(item.id)
            else:
                report.merged_mentions += 1
                if item.id in existing_ids:
                    report.updated_items.add(item.id)
    report.skipped.sort()
    return report
