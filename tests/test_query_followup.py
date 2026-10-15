import json
from datetime import date
from pathlib import Path

import pytest

from actiontrack.drafter import OutboxDrafter, PrintDrafter
from actiontrack.followup import compose_followup, items_for
from actiontrack.models import ActionTrackError, Item, Mention
from actiontrack.query import PersonNotFound, filter_items, is_overdue, resolve_person

TODAY = date(2026, 10, 15)
PEOPLE = ["Priya Nair", "Priya Shah", "Arjun Mehta"]


def item(id, task, owners=("Priya Shah",), due=None, status="open", owner_status="resolved", candidates=()):
    mention = Mention(file="2026-10-14-sync.md", line=id, meeting_date="2026-10-14", meeting_title="Sprint sync",
                      checked=status == "done", raw=task, task=task, due=due, due_raw=None,
                      due_status="resolved" if due else "none")
    return Item(id=id, task=task, owner_status=owner_status, owners=list(owners), owner_raw=None,
                owner_label=None, candidates=list(candidates), due=due, due_raw=None,
                due_status="resolved" if due else "none", status=status, done_by=None, done_at=None,
                first_seen="2026-10-14", mentions=[mention])


ITEMS = [
    item(1, "send the revised quote", due="2026-10-16"),
    item(2, "share the meeting minutes", due="2026-09-04"),
    item(3, "fix the login bug", owners=("Arjun Mehta",), due="2026-09-04"),
    item(4, "update the test plan", owners=("Arjun Mehta",), due="2026-10-31"),
    item(5, "circulate the retro notes", owners=(), owner_status="ambiguous",
         candidates=("Priya Nair", "Priya Shah")),
    item(6, "review the release checklist", owners=(), owner_status="unassigned", due="2026-10-16"),
    item(7, "close the vendor contract", owners=("Priya Shah",), due="2026-10-15"),
    item(8, "book the demo room", owners=("Arjun Mehta",), status="done"),
]


def ids(items):
    return [i.id for i in items]


def test_overdue_is_strictly_before_today_and_never_done():
    assert is_overdue(ITEMS[1], TODAY)
    assert not is_overdue(ITEMS[6], TODAY)  # due today
    assert not is_overdue(item(9, "x", due="2026-01-01", status="done"), TODAY)
    assert not is_overdue(ITEMS[4], TODAY)  # no due date


def test_status_filters():
    assert ids(filter_items(ITEMS, today=TODAY, status="overdue")) == [2, 3]
    assert 8 not in ids(filter_items(ITEMS, today=TODAY, status="open"))
    assert set(ids(filter_items(ITEMS, today=TODAY, status="open"))) == {1, 2, 3, 4, 5, 6, 7}
    assert ids(filter_items(ITEMS, today=TODAY, status="done")) == [8]


def test_owner_filter_excludes_ambiguous_items():
    assert set(ids(filter_items(ITEMS, today=TODAY, owner="priya shah", people=PEOPLE))) == {1, 2, 7}


def test_special_owner_values():
    assert ids(filter_items(ITEMS, today=TODAY, owner="ambiguous")) == [5]
    assert ids(filter_items(ITEMS, today=TODAY, owner="unassigned")) == [6]


def test_due_before_is_exclusive_and_skips_undated():
    assert set(ids(filter_items(ITEMS, today=TODAY, due_before=date(2026, 10, 16)))) == {2, 3, 7}


def test_filters_combine():
    got = filter_items(ITEMS, today=TODAY, owner="Arjun Mehta", status="overdue",
                       due_before=date(2026, 10, 1), people=PEOPLE)
    assert ids(got) == [3]


def test_sorting_overdue_first_then_due_then_undated_then_done():
    assert ids(filter_items(ITEMS, today=TODAY)) == [2, 3, 7, 1, 6, 4, 5, 8]


def test_person_lookup():
    assert resolve_person("arjun", PEOPLE) == "Arjun Mehta"
    with pytest.raises(ActionTrackError, match="Priya Nair, Priya Shah"):
        resolve_person("Priya", PEOPLE)
    with pytest.raises(PersonNotFound):
        resolve_person("Unknown Person", PEOPLE)


def test_followup_overdue_first_and_excludes_done_ambiguous_unassigned():
    mine = items_for(ITEMS, "Priya Shah")
    assert set(ids(mine)) == {1, 2, 7}
    draft = compose_followup("Priya Shah", "priya.shah@example.com", mine, TODAY)
    assert draft.to == "priya.shah@example.com"
    assert draft.item_ids == [2, 7, 1]
    assert draft.subject.startswith("Action items follow-up: 3 open (1 overdue)")
    body = draft.body
    assert body.startswith("Hi Priya,")
    assert body.index("OVERDUE") < body.index("Share the meeting minutes") < body.index("COMING UP")
    assert "41 days overdue" in body
    assert "retro notes" not in body and "release checklist" not in body
    for marker in ("**", "# ", "* "):  # Gmail body must be plain text, not markdown
        assert marker not in body


def test_undated_section():
    draft = compose_followup("Arjun Mehta", "a@example.com", items_for(ITEMS, "Arjun Mehta"), TODAY)
    assert draft.item_ids == [3, 4]
    mine = [item(10, "book the room", owners=("Arjun Mehta",))]
    assert "NO DUE DATE YET" in compose_followup("Arjun Mehta", "a@example.com", mine, TODAY).body


def test_outbox_drafter_writes_json(tmp_path):
    draft = compose_followup("Priya Shah", "p@example.com", items_for(ITEMS, "Priya Shah"), TODAY)
    path = Path(OutboxDrafter(tmp_path / "outbox").submit(draft))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["to"] == "p@example.com" and data["item_ids"] == [2, 7, 1]
    assert path.name.startswith("priya-shah-")


def test_print_drafter(capsys):
    draft = compose_followup("Priya Shah", "p@example.com", items_for(ITEMS, "Priya Shah"), TODAY)
    assert "dry run" in PrintDrafter().submit(draft)
    assert "To:      p@example.com" in capsys.readouterr().out


def test_no_send_code_exists():
    source = Path(__file__).parent.parent / "src" / "actiontrack"
    banned = ("send_message", "smtplib", ".forward(", ".reply(", "send_mail", "sendmail")
    for path in source.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for word in banned:
            assert word not in text, f"{word} found in {path.name}"
