from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from actiontrack.cli import main
from actiontrack.models import Note

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "sample_notes"
PEOPLE_YAML = Path(__file__).parent.parent / "people.yaml"
TODAY = "2026-10-15"


def make_note(text: str, name: str = "2026-10-14-test.md", meeting: date = date(2026, 10, 14),
              attendees: list[str] | None = None) -> Note:
    return Note(path=Path(name), title="Test", meeting_date=meeting, attendees=attendees or [],
                lines=text.split("\n"), body_start=0)


@pytest.fixture
def cli(tmp_path, capsys):
    """Run the CLI against a temp store; returns (exit_code, stdout, stderr)."""
    store = tmp_path / "store.json"

    def run(*args: str, today: str = TODAY):
        code = main([*args, "--store", str(store), "--people", str(PEOPLE_YAML), "--today", today])
        out = capsys.readouterr()
        return code, out.out, out.err

    run.store = store
    return run


@pytest.fixture
def ingested(cli):
    code, _, _ = cli("ingest", str(SAMPLE))
    assert code == 0
    return cli
