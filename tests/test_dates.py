from datetime import date

import pytest

from actiontrack.dates import resolve_due

D = date.fromisoformat


@pytest.mark.parametrize("meeting, text, due", [
    ("2026-09-01", "send the revised quote to Acme by Friday", "2026-09-04"),  # Tue -> Fri
    ("2026-10-16", "raise the budget request by Friday", "2026-10-23"),        # Fri -> next Fri
    ("2026-09-18", "audit colour contrast by Mon", "2026-09-21"),
    ("2026-09-25", "triage the open bug list by Monday", "2026-09-28"),
    ("2026-10-10", "send the proposal by Tuesday", "2026-10-13"),             # Saturday meeting
    ("2026-09-08", "finish login screen by Wed", "2026-09-09"),
    ("2026-10-05", "start SSO spike by next Tuesday", "2026-10-13"),
    ("2026-09-02", "open the repo access request by tomorrow", "2026-09-03"),
    ("2026-09-21", "write the postmortem by EOD tomorrow", "2026-09-22"),
    ("2026-10-08", "circulate the summary by EOD", "2026-10-08"),
    ("2026-09-03", "draft the test plan by end of next week", "2026-09-11"),
    ("2026-09-21", "ship it by EOW", "2026-09-25"),
    ("2026-09-14", "collect quotes by end of month", "2026-09-30"),
    ("2026-02-11", "close the vendor contract by end of month", "2026-02-28"),
    ("2026-09-30", "propose the on-call rotation by mid-October", "2026-10-15"),
    ("2026-09-30", "finalise the Q4 sales targets by Oct 3rd", "2026-10-03"),
    ("2026-09-03", "export last quarter invoices by 10 Sep", "2026-09-10"),
    ("2026-09-14", "finalise the welcome-email copy by Wed 16 Sep", "2026-09-16"),
    ("2026-09-30", "run the customer survey, results due 15 October", "2026-10-15"),
    ("2026-10-06", "demo the portal to Acme on 2026-10-14", "2026-10-14"),
    ("2026-09-01", "set up staging by 2026-09-08", "2026-09-08"),
    ("2026-09-30", "circulate the offsite summary tomorrow", "2026-10-01"),
    ("2026-12-20", "renew the licence by 5 Jan", "2027-01-05"),               # year rollover
])
def test_due_phrases_resolve_from_meeting_date(meeting, text, due):
    result = resolve_due(text, D(meeting))
    assert result.due == D(due)
    assert result.status == "resolved"


@pytest.mark.parametrize("text, task", [
    ("send revised quote to Acme — by Friday", "send revised quote to Acme"),
    ("run the customer survey, results due 15 October", "run the customer survey"),
    ("cut cloud costs by 10% — proposal by 2026-10-09", "cut cloud costs by 10% — proposal"),
    ("collect user feedback by 2026-09-25 (with Priya Nair)", "collect user feedback (with Priya Nair)"),
])
def test_due_clause_is_removed_from_task(text, task):
    assert resolve_due(text, D("2026-10-02")).task == task


def test_percent_is_not_a_date():
    r = resolve_due("cut cloud costs by 10% — proposal by 2026-10-09", D("2026-10-02"))
    assert r.due == D("2026-10-09")


@pytest.mark.parametrize("text", [
    "freeze invoice edits from 9 Oct",
    "schedule cutover for Saturday 10 Oct",
    "schedule the quarterly business review for November",
    "book the demo room",
])
def test_non_deadlines_give_no_due_date(text):
    r = resolve_due(text, D("2026-09-29"))
    assert (r.due, r.raw, r.status, r.task) == (None, None, "none", text)


@pytest.mark.parametrize("text, raw", [
    ("snapshot the production DB before cutover", "before cutover"),
    ("review the prototype before the next review", "before the next review"),
    ("share the deck by the next sprint", "by the next sprint"),
])
def test_unrecognised_phrases_are_unresolved_not_guessed(text, raw):
    r = resolve_due(text, D("2026-09-03"))
    assert (r.due, r.raw, r.status) == (None, raw, "unresolved")
