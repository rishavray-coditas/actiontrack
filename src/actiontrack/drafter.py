"""Where a composed follow-up goes. This is the only swappable hand-off point.

actiontrack never sends email. `OutboxDrafter` writes a draft request that the
`/actiontrack-followup` Claude Code skill turns into a Gmail *draft* via the
Gmail MCP connector; `PrintDrafter` just prints it (dry run).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Protocol, TextIO

from .followup import Draft


class Drafter(Protocol):
    def submit(self, draft: Draft) -> str:
        """Hand the draft over; return a short description of where it went."""


class PrintDrafter:
    def __init__(self, stream: TextIO | None = None):
        self.stream = stream or sys.stdout

    def submit(self, draft: Draft) -> str:
        print(f"To:      {draft.to}", file=self.stream)
        print(f"Subject: {draft.subject}", file=self.stream)
        print("", file=self.stream)
        print(draft.body, file=self.stream, end="")
        return "printed (dry run; no draft created)"


class OutboxDrafter:
    def __init__(self, outbox_dir: Path):
        self.outbox_dir = outbox_dir

    def submit(self, draft: Draft) -> str:
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", draft.owner.lower()).strip("-")
        path = self.outbox_dir / f"{slug}-{datetime.now():%Y%m%dT%H%M%S}.json"
        path.write_text(json.dumps(draft.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return str(path)
