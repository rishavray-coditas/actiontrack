"""End-to-end tests on the provided sample notes, run through the CLI with today = 2026-10-15."""
import hashlib
import json

import pytest

from .conftest import SAMPLE


def listing(cli, *args):
    code, out, err = cli("list", "--json", *args)
    assert code == 0, err
    return json.loads(out)


def find(items, owner, text):
    hits = [i for i in items if owner in (i["owner"]) and text in i["task"]]
    assert len(hits) == 1, (owner, text, hits)
    return hits[0]


def test_ingest_summary(cli):
    code, out, _ = cli("ingest", str(SAMPLE))
    assert code == 0
    assert "Scanned 36 files: 31 ingested, 4 skipped, 1 ignored" in out
    for line in ("2026-09-09-notes-final-v2.md  empty file",
                 "2026-10-03-sales-pipeline.md  unparseable date 'sometime last week'",
                 "2026-09-19-offsite-draft.txt  not a .md file"):
        assert line in out
    assert "Ambiguous owner (6)" in out
    assert "Unassigned (5)" in out


def test_reingest_adds_nothing_and_keeps_ids(ingested):
    before = listing(ingested)
    code, out, _ = ingested("ingest", str(SAMPLE))
    assert code == 0
    assert "Items: 0 new, 0 updated" in out
    assert listing(ingested) == before


@pytest.mark.parametrize("owner, text, due", [
    ("Anita Desai", "share first wireframes", "2026-09-03"),
    ("Lena Fischer", "pull Acme's usage report", "2026-09-11"),          # 09-10 "by tomorrow"
    ("Anita Desai", "audit colour contrast", "2026-09-21"),              # Fri "by Mon"
    ("Priya Shah", "triage the open bug list", "2026-09-28"),            # Fri "by Monday"
    ("Meera Iyer", "send the proposal to Orbit Labs", "2026-10-13"),     # Sat "by Tuesday"
    ("Priya Shah", "draft the test plan for invoice rounding", "2026-09-11"),
    ("Lena Fischer", "collect 5 customer quotes", "2026-10-02"),         # later mention moved the date
    ("Sam Okafor", "propose the on-call rotation", "2026-10-15"),
    ("Sam Okafor", "write the postmortem", "2026-09-22"),
    ("Rahul Verma", "start SSO spike", "2026-10-13"),
    ("Anita Desai", "refresh the brand kit", "2026-10-09"),              # from a table row
    ("Karan Joshi", "circulate the offsite summary", "2026-10-01"),      # ACTION: line
    ("Sam Okafor", "cut cloud costs by 10%", "2026-10-09"),
])
def test_golden_due_dates(ingested, owner, text, due):
    assert find(listing(ingested), owner, text)["due"] == due


def test_duplicates_appear_once(ingested):
    items = listing(ingested)
    wire = find(items, "Anita Desai", "share updated wireframes")
    assert len(wire["sources"]) == 2 and wire["overdue"]
    beta = find(items, "Rahul Mehta", "deploy the beta to staging")
    assert len(beta["sources"]) == 3 and beta["status"] == "done"
    freeze = find(items, "Karan Joshi", "freeze invoice edits from 9 Oct")
    assert len(freeze["sources"]) == 2 and freeze["due"] is None
    pagination = find(items, "Rahul Mehta", "fix the pagination bug")
    assert pagination["due"] == "2026-09-23" and pagination["overdue"]
    assert find(items, "Meera Iyer", "book the renewal call")["status"] == "done"
    assert find(items, "Priya Nair", "revised quote")["status"] == "done"


def test_traps_are_not_items(ingested):
    tasks = [i["task"] for i in listing(ingested)]
    assert not any("hardware tokens" in t for t in tasks)    # HTML comment
    assert not any("remediate finding" in t for t in tasks)  # code fence
    assert sum("refund affected customers" in t for t in tasks) == 1  # blockquote copy ignored
    assert not any("Book the venue" in t for t in tasks)    # .txt file
    assert not any("chase Orbit Labs" in t for t in tasks)  # skipped bad-date note


def test_ambiguous_unassigned_and_no_due_items_are_visible(ingested):
    ambiguous = listing(ingested, "--owner", "ambiguous")
    assert {i["task"] for i in ambiguous} == {
        "sign off the cutover checklist", "rebase the feature branch", "own the hiring plan for the two QA roles",
        "prepare the architecture overview", "review Anita's PR", "circulate the go/no-go summary"}
    assert len(listing(ingested, "--owner", "unassigned")) == 5
    assert find(listing(ingested), "Sam Okafor", "snapshot the production DB")["due_status"] == "unresolved"


def test_list_filters_and_combinations(ingested):
    overdue = listing(ingested, "--status", "overdue")
    assert overdue and all(i["overdue"] for i in overdue)
    assert all(i["due"] is not None for i in overdue)
    nair = listing(ingested, "--owner", "Priya Nair", "--due-before", "2026-10-20")
    assert nair and all("Priya Nair" in i["owners"] and i["due"] < "2026-10-20" for i in nair)
    combo = listing(ingested, "--owner", "Rahul Mehta", "--status", "overdue", "--due-before", "2026-09-20")
    assert [i["task"] for i in combo] == ["open the repo access request", "finish login screen"]
    assert all(i["status"] == "done" for i in listing(ingested, "--status", "done"))


def test_list_table_marks_overdue(ingested):
    code, out, _ = ingested("list", "--status", "overdue")
    assert code == 0 and "OVERDUE" in out and "\033[" not in out  # no colour codes when piped


def test_ambiguous_first_name_errors_with_candidates(ingested):
    code, _, err = ingested("list", "--owner", "Priya")
    assert code == 1 and "Priya Nair, Priya Shah" in err
    code, out, err = ingested("list", "--owner", "Nobody Here")
    assert code == 0 and "No items" in err


def test_done_flow(ingested):
    item = find(listing(ingested), "Rahul Mehta", "fix the pagination bug")
    code, out, _ = ingested("done", str(item["id"]))
    assert code == 0 and "Marked item" in out
    assert item["id"] not in [i["id"] for i in listing(ingested, "--status", "overdue")]
    assert item["id"] in [i["id"] for i in listing(ingested, "--status", "done")]
    code, out, _ = ingested("done", str(item["id"]))
    assert code == 0 and "already done" in out
    ingested("ingest", str(SAMPLE))  # a re-ingest must not reopen it
    assert item["id"] in [i["id"] for i in listing(ingested, "--status", "done")]


@pytest.mark.parametrize("arg", ["99999", "abc"])
def test_done_invalid_id(ingested, arg):
    code, _, err = ingested("done", arg)
    assert code == 1 and "error:" in err


def test_followup_dry_run(ingested):
    code, out, _ = ingested("followup", "Priya Nair", "--dry-run", "--json")
    assert code == 0
    draft = json.loads(out)
    assert draft["status"] == "dry_run" and draft["to"] == ["priya.nair@example.com"][0]
    body = draft["body"]
    assert body.index("OVERDUE") < body.index("COMING UP")
    assert "Prepare the renewal one-pager" in body
    assert "hiring plan" not in body  # ambiguous Priya item
    assert "revised quote" not in body  # done item
    assert not ingested.store.parent.joinpath("outbox").exists()


def test_followup_writes_outbox_never_sends(ingested):
    code, out, _ = ingested("followup", "Lena Fischer", "--json")
    assert code == 0
    data = json.loads(out)
    assert data["status"] == "ready"
    saved = json.loads(open(data["outbox_file"], encoding="utf-8").read())
    assert saved["to"] == "lena.fischer@example.com" and saved["item_ids"] == data["item_ids"]


def test_followup_errors(ingested, tmp_path):
    code, _, err = ingested("followup", "Rahul")
    assert code == 1 and "Rahul Mehta, Rahul Verma" in err
    code, _, err = ingested("followup", "Ravi Kumar")
    assert code == 1 and "no one called" in err


def test_followup_nothing_open(ingested):
    items = listing(ingested, "--owner", "Lena Fischer", "--status", "open")
    for i in items:
        ingested("done", str(i["id"]))
    code, out, _ = ingested("followup", "Lena Fischer")
    assert code == 0 and "Nothing to follow up" in out


def test_usage_errors_exit_2(cli):
    for args in (["foo"], ["ingest"], ["list", "--status", "pending"], ["list", "--due-before", "Friday"],
                 ["list", "--due-before", "2026-13-45"], ["done"], ["followup"]):
        with pytest.raises(SystemExit) as exc:
            cli(*args)
        assert exc.value.code == 2


def test_missing_folder(cli, tmp_path):
    code, _, err = cli("ingest", str(tmp_path / "missing"))
    assert code == 1 and "folder not found" in err
    assert not cli.store.exists()


def test_empty_folder(cli, tmp_path):
    (tmp_path / "empty").mkdir()
    code, out, _ = cli("ingest", str(tmp_path / "empty"))
    assert code == 0 and "Scanned 0 files" in out


def test_notes_are_never_modified(cli):
    def digest():
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in SAMPLE.iterdir()}
    before = digest()
    cli("ingest", str(SAMPLE))
    cli("list")
    cli("done", "1")
    cli("followup", "Priya Nair", "--dry-run")
    assert digest() == before
