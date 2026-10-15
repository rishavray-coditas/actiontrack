"""The item store: one JSON file with stable, never-reused item IDs."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .models import ActionTrackError, Item

SCHEMA_VERSION = 1
STORE_ENV = "ACTIONTRACK_STORE"


def default_store_path(explicit: Path | None = None) -> Path:
    if explicit:
        return explicit
    if env := os.environ.get(STORE_ENV):
        return Path(env)
    return Path.home() / ".actiontrack" / "store.json"


class Store:
    def __init__(self, path: Path, items: list[Item] | None = None, next_id: int = 1):
        self.path = path
        self.items: list[Item] = items or []
        self.next_id = next_id

    @classmethod
    def load(cls, path: Path) -> "Store":
        if not path.exists():
            return cls(path)
        try:
            text = path.read_text(encoding="utf-8")
            if not text.strip():
                return cls(path)
            data = json.loads(text)
            if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
                raise ValueError(f"expected schema_version {SCHEMA_VERSION}")
            items = [Item.from_dict(d) for d in data["items"]]
            next_id = int(data["next_id"])
        except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
            raise ActionTrackError(
                f"item store {path} is unreadable or corrupted ({exc}). "
                "Fix it or move it aside; it has not been changed."
            ) from None
        next_id = max([next_id, *(i.id + 1 for i in items)])
        return cls(path, items, next_id)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "next_id": self.next_id,
            "items": [item.to_dict() for item in self.items],
        }
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def get(self, item_id: int) -> Item | None:
        return next((i for i in self.items if i.id == item_id), None)

    def add(self, item: Item) -> Item:
        item.id = self.next_id
        self.next_id += 1
        self.items.append(item)
        return item
