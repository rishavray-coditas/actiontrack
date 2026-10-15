"""Human-readable output: the ingest summary and the `list` table."""
from __future__ import annotations

import re
import shutil
from datetime import date

from .models import IngestReport, Item
from .query import days_overdue, is_overdue

RED, DIM, BOLD, RESET = "\033[31m", "\033[2m", "\033[1m", "\033[0m"
MAX_LISTED = 12


def owner_display(item: Item) -> str:
    if item.owner_status == "resolved":
        return ", ".join(item.owners)
    if item.owner_status == "ambiguous":
        text = "? " + " / ".join(item.candidates)
        return ", ".join(item.owners) + " + " + text if item.owners else text
    if item.owner_status == "unknown":
        return f"unknown: {item.owner_raw}"
    return f"unassigned ({item.owner_label})" if item.owner_label else "unassigned"


def due_display(item: Item) -> str:
    if item.due:
        return item.due
    if item.due_raw:
        return f"? {item.due_raw}"
    return "-"


def status_display(item: Item, today: date) -> str:
    if is_overdue(item, today):
        return f"OVERDUE {days_overdue(item, today)}d"
    return item.status


def source_display(item: Item) -> str:
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}[-_]?", "", item.latest.file.rsplit(".", 1)[0])
    extra = f" (+{len(item.mentions) - 1})" if len(item.mentions) > 1 else ""
    return f"{item.latest.meeting_date} {stem}{extra}"


def render_items(items: list[Item], today: date, color: bool = False, width: int | None = None) -> str:
    headers = ["ID", "Status", "Due", "Owner", "Task", "From"]
    rows = [
        [str(i.id), status_display(i, today), due_display(i), owner_display(i), i.task, source_display(i)]
        for i in items
    ]
    widths = [max(len(h), *(len(r[c]) for r in rows)) for c, h in enumerate(headers)]
    if width:
        fixed = sum(w for c, w in enumerate(widths) if c != 4) + 2 * (len(headers) - 1)
        widths[4] = max(24, min(widths[4], width - fixed))

    def fmt(cells):
        out = []
        for c, cell in enumerate(cells):
            if len(cell) > widths[c]:
                cell = cell[: widths[c] - 1] + "…"
            out.append(cell.ljust(widths[c]))
        return "  ".join(out).rstrip()

    lines = [fmt(headers), fmt(["-" * w for w in widths])]
    for item, row in zip(items, rows):
        line = fmt(row)
        if color and is_overdue(item, today):
            line = f"{RED}{BOLD}{line}{RESET}"
        elif color and item.status == "done":
            line = f"{DIM}{line}{RESET}"
        lines.append(line)
    overdue = sum(is_overdue(i, today) for i in items)
    lines.append("")
    lines.append(f"{len(items)} item{'s' if len(items) != 1 else ''}, {overdue} overdue (as of {today.isoformat()})")
    return "\n".join(lines)


def terminal_width() -> int:
    return shutil.get_terminal_size((120, 24)).columns


def render_ingest_report(report: IngestReport, items: list[Item], today: date) -> str:
    out = [
        f"Scanned {report.scanned} files: {len(report.ingested)} ingested, "
        f"{len(report.skipped)} skipped, {len(report.ignored)} ignored"
    ]
    out += _section("Skipped", report.skipped)
    out += _section("Ignored", report.ignored)
    out += _section("Warnings", report.warnings)
    out.append(
        f"Items: {len(report.new_items)} new, {len(report.updated_items)} updated, "
        f"{report.known_mentions} already known; {report.merged_mentions} repeated mentions merged. "
        f"Store now holds {len(items)} items."
    )
    open_items = [i for i in items if i.status != "done"]
    attention = [
        ("Ambiguous owner", [i for i in open_items if i.owner_status == "ambiguous"]),
        ("Unknown owner", [i for i in open_items if i.owner_status == "unknown"]),
        ("Unassigned", [i for i in open_items if i.owner_status == "unassigned"]),
        ("Unresolved due phrase", [i for i in open_items if i.due_status == "unresolved"]),
    ]
    if any(group for _, group in attention):
        out.append("Needs attention (open items):")
        for label, group in attention:
            if group:
                out.append(f"  {label} ({len(group)}):")
                for item in group:
                    out.append(f"    #{item.id:<4} {owner_display(item):<28} {item.task}  [{due_display(item)}]")
    overdue = sum(is_overdue(i, today) for i in items)
    out.append(f"Overdue as of {today.isoformat()}: {overdue}. Run `actiontrack list --status overdue` to see them.")
    return "\n".join(out)


def _section(title: str, rows: list[tuple[str, str]]) -> list[str]:
    if not rows:
        return []
    width = min(40, max(len(name) for name, _ in rows))
    lines = [f"{title}:"]
    lines += [f"  {name:<{width}}  {reason}" for name, reason in rows]
    return lines
