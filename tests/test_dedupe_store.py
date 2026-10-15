import json

import pytest

from actiontrack.dedupe import merge, similarity, tokens
from actiontrack.ingest import build_candidates
from actiontrack.models import ActionTrackError
from actiontrack.reader import read_note
from actiontrack.store import Store

from .conftest import SAMPLE

ROSTER = ["Priya Nair", "Priya Shah", "Rahul Mehta", "Rahul Verma", "Anita Desai", "Sam Okafor",
          "Meera Iyer", "Karan Joshi", "Lena Fischer"]


def ingest_files(store, *names):
    for name in names:
        for cand in build_candidates(read_note(SAMPLE / name), ROSTER):
            merge(store, cand)


def test_reworded_items_normalise_to_the_same_tokens():
    a = tokens("send the revised quote to Acme")
    b = tokens("send revised quote to Acme")
    assert a == b
    assert similarity(tokens("estimate the SSO work"), tokens("estimate SSO work")) == 1.0
    assert similarity(tokens("share first wireframes"), tokens("share updated wireframes")) < 0.8


def test_repeated_reworded_item_merges_and_later_x_closes_it(tmp_path):
    store = Store(tmp_path / "s.json")
    ingest_files(store, "2026-09-01-quote-portal-kickoff.md", "2026-09-08-quote-portal-weekly.md",
                 "2026-09-15-quote-portal-weekly.md")
    quote = [i for i in store.items if "revised quote" in i.task]
    assert len(quote) == 1
    item = quote[0]
    assert item.owners == ["Priya Nair"]
    assert len(item.mentions) == 3
    assert (item.status, item.done_by, item.done_at) == ("done", "note", "2026-09-15")
    assert item.due == "2026-09-11"  # latest mention that states a date: 09-08 "by Friday"


def test_same_text_different_owner_stays_separate(tmp_path):
    store = Store(tmp_path / "s.json")
    ingest_files(store, "2026-09-22-quote-portal-weekly.md", "2026-09-25-qa-sync.md")
    owners = {tuple(i.owners) for i in store.items if i.task.startswith("fix the")}
    assert owners == {("Rahul Mehta",), ("Rahul Verma",)}


def test_reingest_is_idempotent_and_ids_are_stable(tmp_path):
    store = Store(tmp_path / "s.json")
    files = sorted(p.name for p in SAMPLE.glob("2026-09-*.md") if p.stat().st_size)
    ingest_files(store, *files)
    before = {i.id: (i.task, len(i.mentions)) for i in store.items}
    ingest_files(store, *files)
    assert {i.id: (i.task, len(i.mentions)) for i in store.items} == before


def test_manual_done_survives_reingest(tmp_path):
    store = Store(tmp_path / "s.json")
    ingest_files(store, "2026-09-15-quote-portal-weekly.md")
    item = next(i for i in store.items if "pagination" in i.task)
    item.status, item.done_by, item.done_at = "done", "manual", "2026-10-15"
    ingest_files(store, "2026-09-22-quote-portal-weekly.md")  # repeats it as open
    assert item.status == "done" and item.done_by == "manual"
    assert len(item.mentions) == 2


def test_store_round_trip_and_atomic_write(tmp_path):
    path = tmp_path / "store.json"
    store = Store(path)
    ingest_files(store, "2026-09-01-quote-portal-kickoff.md")
    store.save()
    assert not (tmp_path / "store.json.tmp").exists()
    loaded = Store.load(path)
    assert [i.to_dict() for i in loaded.items] == [i.to_dict() for i in store.items]
    assert loaded.next_id == 5


def test_ids_are_never_reused(tmp_path):
    path = tmp_path / "store.json"
    store = Store(path)
    ingest_files(store, "2026-09-01-quote-portal-kickoff.md")
    store.items.pop()  # even if an item disappears, its ID is not handed out again
    store.save()
    assert Store.load(path).next_id == 5


@pytest.mark.parametrize("content", ["{not json", json.dumps({"schema_version": 99, "items": []}), "[]"])
def test_corrupted_store_is_a_clear_error_and_untouched(tmp_path, content):
    path = tmp_path / "store.json"
    path.write_text(content)
    with pytest.raises(ActionTrackError, match="corrupted"):
        Store.load(path)
    assert path.read_text() == content


def test_missing_or_empty_store_is_empty(tmp_path):
    assert Store.load(tmp_path / "none.json").items == []
    (tmp_path / "empty.json").write_text("")
    assert Store.load(tmp_path / "empty.json").items == []
