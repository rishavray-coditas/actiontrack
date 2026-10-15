import pytest

from actiontrack.owners import match_names, resolve_owner, split_owner

ROSTER = ["Priya Nair", "Priya Shah", "Rahul Mehta", "Rahul Verma", "Anita Desai", "Sam Okafor",
          "Meera Iyer", "Karan Joshi", "Lena Fischer"]


def test_first_name_resolves_to_single_attendee():
    r = resolve_owner("Priya to send the revised quote to Acme by Friday", ["Priya Nair", "Rahul Mehta"], ROSTER)
    assert (r.status, r.owners, r.task) == ("resolved", ["Priya Nair"], "send the revised quote to Acme by Friday")


def test_owner_resolved_per_meeting_not_globally():
    r = resolve_owner("Priya to review the welcome email", ["Anita Desai", "Priya Shah"], ROSTER)
    assert r.owners == ["Priya Shah"]


def test_same_first_name_is_ambiguous_never_guessed():
    r = resolve_owner("Priya to sign off the cutover checklist", ["Priya Shah", "Priya Nair", "Sam Okafor"], ROSTER)
    assert r.status == "ambiguous"
    assert r.owners == []
    assert r.candidates == ["Priya Nair", "Priya Shah"]


@pytest.mark.parametrize("text, expected", [
    ("Priya N. to notify customers", "Priya Nair"),
    ("Priya S. to run the invoice rounding tests", "Priya Shah"),
    ("Priya Nair to notify customers", "Priya Nair"),
])
def test_surname_initial_or_full_name_disambiguates(text, expected):
    r = resolve_owner(text, ["Priya Shah", "Priya Nair"], ROSTER)
    assert (r.status, r.owners) == ("resolved", [expected])


def test_handle():
    r = resolve_owner("@anita: audit colour contrast on the dashboard by Mon", ["Anita Desai"], ROSTER)
    assert (r.owners, r.task) == (["Anita Desai"], "audit colour contrast on the dashboard by Mon")


def test_two_owners():
    r = resolve_owner("Anita & Rahul to agree on the component API", ["Anita Desai", "Rahul Mehta"], ROSTER)
    assert (r.status, r.owners) == ("resolved", ["Anita Desai", "Rahul Mehta"])


def test_helper_is_not_an_owner():
    r = resolve_owner("Lena (with Priya) to collect user feedback", ["Lena Fischer", "Priya Nair"], ROSTER)
    assert r.owners == ["Lena Fischer"]
    assert r.task == "collect user feedback (with Priya Nair)"


@pytest.mark.parametrize("text, label", [
    ("Someone to update the CRM notes", "Someone"),
    ("TBD to write the design-system changelog", "TBD"),
    ("Everyone to review the prototype", "Everyone"),
    ("Team to decide on the launch date", "Team"),
])
def test_placeholders_and_groups_are_unassigned(text, label):
    r = resolve_owner(text, ["Anita Desai"], ROSTER)
    assert (r.status, r.owners, r.label) == ("unassigned", [], label)


def test_no_owner():
    r = resolve_owner("Book the venue", ["Anita Desai"], ROSTER)
    assert (r.status, r.raw, r.task) == ("unassigned", None, "Book the venue")


def test_not_an_attendee_falls_back_to_roster_with_warning():
    r = resolve_owner("Lena to send the deck", ["Anita Desai"], ROSTER)
    assert r.owners == ["Lena Fischer"]
    assert r.warnings and "not in the attendee list" in r.warnings[0]


def test_no_attendees_and_shared_first_name_is_ambiguous():
    r = resolve_owner("Rahul to rebase the feature branch", [], ROSTER)
    assert r.status == "ambiguous"
    assert r.candidates == ["Rahul Mehta", "Rahul Verma"]


def test_unknown_name_is_kept():
    r = resolve_owner("Ravi to send the logs", ["Anita Desai"], ROSTER)
    assert (r.status, r.raw) == ("unknown", "Ravi")


def test_first_to_is_the_split_point():
    assert split_owner("Meera to send Acme the procurement form to legal") == (
        "Meera", "send Acme the procurement form to legal")


def test_sentence_starting_with_a_verb_is_not_an_owner():
    assert split_owner("Send the deck to Acme") == (None, "Send the deck to Acme")


def test_match_names_case_insensitive():
    assert match_names("priya nair", ROSTER) == ["Priya Nair"]
    assert match_names("rahul", ROSTER) == ["Rahul Mehta", "Rahul Verma"]
    assert match_names("Nobody", ROSTER) == []
