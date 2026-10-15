from actiontrack.extractor import extract_items
from actiontrack.reader import read_note

from .conftest import SAMPLE, make_note


def texts(name):
    return [i.text for i in extract_items(read_note(SAMPLE / name))]


def test_blockquoted_checkbox_is_ignored():
    assert texts("2026-09-21-incident-review.md") == [
        "Sam to write the postmortem by EOD tomorrow",
        "Rahul to add idempotency keys to the payment call by Friday",
        "Priya to add a regression test for double charge by 25 Sep",
        "Karan to refund affected customers",
    ]


def test_code_fence_and_html_comment_are_ignored():
    assert texts("2026-10-09-security-review.md") == [
        "Sam to enable MFA on all admin accounts by 2026-10-16",
        "Rahul to patch the outdated express dependency by Monday",
        "Priya to document the incident response steps by 23 Oct",
        "Karan to revoke access for the two ex-contractors",
    ]


def test_offsite_formats_nested_star_plus_table_and_action():
    items = extract_items(read_note(SAMPLE / "2026-09-30-q4-offsite.md"))
    got = {i.text: i.kind for i in items}
    assert got == {
        "Meera to finalise the Q4 sales targets by Oct 3rd": "checkbox",
        "Karan to validate targets against the budget by Oct 5th": "checkbox",
        "Lena to run the customer survey, results due 15 October": "checkbox",
        "Sam to propose the on-call rotation by mid-October": "checkbox",
        "Priya to own the hiring plan for the two QA roles": "checkbox",
        "Rahul to prepare the architecture overview by Friday": "checkbox",
        "Everyone to submit their Q4 goals by 7 Oct": "checkbox",
        "Anita to refresh the brand kit by 2026-10-09": "table",
        "Karan to circulate the offsite summary tomorrow": "action",
    }


def test_checked_marks_and_prose():
    items = extract_items(read_note(SAMPLE / "2026-10-02-finance-sync.md"))  # CRLF file
    assert [(i.text, i.checked) for i in items] == [
        ("Karan to approve the Q4 cloud spend", True),
        ("Sam to cut cloud costs by 10% — proposal by 2026-10-09", False),
        ("Meera to share the Q4 pipeline forecast by Wednesday", False),
        ("Karan to prepare the board finance slide by 12 Oct", False),
    ]


def test_plain_bullets_and_sentences_are_not_items():
    note = make_note("- Discussed Q4 roadmap\nPriya will check with legal.\nSam to propose a cut.\n- [ ] Real item")
    assert [i.text for i in extract_items(note)] == ["Real item"]


def test_multiline_html_comment():
    note = make_note("<!--\n- [ ] hidden one\n-->\n- [ ] visible <!-- note --> item")
    assert [i.text for i in extract_items(note)] == ["visible  item"]


def test_line_numbers_are_recorded():
    note = make_note("# Meeting: x\n\n- [ ] first\n- [x] second")
    assert [(i.line, i.checked) for i in extract_items(note)] == [(3, False), (4, True)]
