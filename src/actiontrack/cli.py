"""Command-line interface: ingest, list, done, followup.

Exit codes: 0 ok, 1 runtime error (clear message, no traceback), 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from . import __version__
from .drafter import OutboxDrafter, PrintDrafter
from .followup import compose_followup, items_for
from .ingest import ingest_folder
from .models import ActionTrackError
from .people import load_people
from .query import STATUSES, PersonNotFound, days_overdue, filter_items, is_overdue, known_people, resolve_person
from .report import due_display, owner_display, render_ingest_report, render_items, terminal_width
from .store import Store, default_store_path

TODAY_ENV = "ACTIONTRACK_TODAY"


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid date '{value}' (expected YYYY-MM-DD, e.g. 2026-10-20)") from None


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--store", type=Path, default=argparse.SUPPRESS,
                        help="item store file (default: $ACTIONTRACK_STORE or ~/.actiontrack/store.json)")
    common.add_argument("--people", type=Path, default=argparse.SUPPRESS,
                        help="people.yaml with names and emails (default: ./people.yaml, then next to the store)")
    common.add_argument("--today", type=_iso_date, default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    parser = argparse.ArgumentParser(
        prog="actiontrack",
        parents=[common],
        description="Track action items from markdown meeting notes and draft follow-up emails. Never sends email.",
    )
    parser.add_argument("--version", action="version", version=f"actiontrack {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")

    p = sub.add_parser("ingest", parents=[common], help="read every .md note in a folder and store its action items")
    p.add_argument("folder", type=Path, help="folder of meeting notes")
    p.set_defaults(handler=cmd_ingest)

    p = sub.add_parser("list", parents=[common], help="show action items (overdue items stand out)")
    p.add_argument("--owner", help="full name, a unique first name, or unassigned / ambiguous / unknown")
    p.add_argument("--status", choices=STATUSES, help="open (includes overdue), done or overdue")
    p.add_argument("--due-before", type=_iso_date, metavar="YYYY-MM-DD",
                   help="only items due strictly before this date")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(handler=cmd_list)

    p = sub.add_parser("done", parents=[common], help="mark an item as done")
    p.add_argument("id", help="item ID, as shown by `list`")
    p.set_defaults(handler=cmd_done)

    p = sub.add_parser("followup", parents=[common],
                       help="draft one follow-up email for an owner's open and overdue items (never sends)")
    p.add_argument("owner", help="the owner's full name (or a unique first name)")
    p.add_argument("--dry-run", action="store_true", help="print the email; create no draft request")
    p.add_argument("--json", action="store_true", help="print the draft as JSON (used by the Claude skill)")
    p.add_argument("--outbox", type=Path, help="folder for draft requests (default: next to the store)")
    p.set_defaults(handler=cmd_followup)
    return parser


class Context:
    def __init__(self, args: argparse.Namespace):
        self.store_path = default_store_path(getattr(args, "store", None))
        self.people_arg = getattr(args, "people", None)
        today = getattr(args, "today", None)
        if today is None and (env := os.environ.get(TODAY_ENV)):
            today = _iso_date(env)
        self.today: date = today or date.today()

    def store(self) -> Store:
        return Store.load(self.store_path)

    def people(self):
        return load_people(self.people_arg, self.store_path.parent)


def cmd_ingest(args, ctx: Context) -> int:
    store = ctx.store()
    people = ctx.people()
    report = ingest_folder(args.folder, store, people.names)
    if report.changed:
        store.save()
    print(render_ingest_report(report, store.items, ctx.today))
    return 0


def cmd_list(args, ctx: Context) -> int:
    store = ctx.store()
    try:
        items = filter_items(
            store.items, today=ctx.today, owner=args.owner, status=args.status,
            due_before=args.due_before, people=ctx.people().names,
        )
    except PersonNotFound as exc:
        print(f"No items: {exc}.", file=sys.stderr)
        items = []
    if args.json:
        print(json.dumps([_item_json(i, ctx.today) for i in items], indent=2, ensure_ascii=False))
        return 0
    if not items:
        print("No items match." if store.items else "The item store is empty. Run `actiontrack ingest <folder>` first.")
        return 0
    color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    if color:
        _enable_windows_ansi()
    print(render_items(items, ctx.today, color=color, width=terminal_width() if sys.stdout.isatty() else None))
    return 0


def cmd_done(args, ctx: Context) -> int:
    raw = args.id.strip().lstrip("#")
    if not raw.isdigit():
        raise ActionTrackError(f"'{args.id}' is not a valid item ID (expected a number such as 12)")
    store = ctx.store()
    item = store.get(int(raw))
    if item is None:
        raise ActionTrackError(f"no item with ID {raw}; run `actiontrack list` to see IDs")
    if item.status == "done":
        print(f"Item {item.id} is already done: {item.task}")
        return 0
    item.status, item.done_by, item.done_at = "done", "manual", ctx.today.isoformat()
    store.save()
    print(f"Marked item {item.id} as done: {item.task} ({owner_display(item)})")
    return 0


def cmd_followup(args, ctx: Context) -> int:
    store = ctx.store()
    people = ctx.people()
    person = resolve_person(args.owner, known_people(store.items, people.names))
    items = items_for(store.items, person)
    if not items:
        if args.json:
            print(json.dumps({"status": "nothing_to_follow_up", "owner": person}))
        else:
            print(f"Nothing to follow up: {person} has no open items. No draft created.")
        return 0
    email = people.emails.get(person)
    if not email:
        where = people.path or "people.yaml (none found)"
        raise ActionTrackError(f"no email address for {person} in {where}; add one and try again. No draft created.")

    draft = compose_followup(person, email, items, ctx.today)
    if args.dry_run:
        if args.json:
            print(json.dumps({"status": "dry_run", **draft.to_dict()}, indent=2, ensure_ascii=False))
        else:
            PrintDrafter().submit(draft)
            print("\n(dry run: nothing was saved, drafted or sent)")
        return 0

    outbox = args.outbox or ctx.store_path.parent / "outbox"
    location = OutboxDrafter(outbox).submit(draft)
    if args.json:
        print(json.dumps({"status": "ready", "outbox_file": location, **draft.to_dict()}, indent=2, ensure_ascii=False))
    else:
        PrintDrafter().submit(draft)
        print(f"\nDraft request saved to {location}")
        print("Nothing was sent. To create the Gmail draft, run /actiontrack-followup in Claude Code.")
    return 0


def _item_json(item, today: date) -> dict:
    return {
        "id": item.id,
        "task": item.task,
        "owner": owner_display(item),
        "owners": item.owners,
        "owner_status": item.owner_status,
        "candidates": item.candidates,
        "due": item.due,
        "due_display": due_display(item),
        "due_status": item.due_status,
        "status": item.status,
        "overdue": is_overdue(item, today),
        "days_overdue": days_overdue(item, today),
        "sources": [f"{m.file}:{m.line}" for m in item.mentions],
    }


def _configure_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _enable_windows_ansi() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:  # noqa: BLE001 - colour is cosmetic
        pass


def main(argv: list[str] | None = None) -> int:
    _configure_streams()
    args = build_parser().parse_args(argv)
    try:
        ctx = Context(args)
        return args.handler(args, ctx)
    except ActionTrackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except argparse.ArgumentTypeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        if os.environ.get("ACTIONTRACK_DEBUG"):
            raise
        print(f"unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def run() -> None:
    sys.exit(main())
