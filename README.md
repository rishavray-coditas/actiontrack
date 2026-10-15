# actiontrack

A small CLI that reads markdown meeting notes and pulls out the action items, such as `- [ ] Priya to send the revised quote by Friday`. It tracks them until they are done and drafts one follow-up email per owner as a **Gmail draft**. **It never sends email.**

```
notes/*.md ──ingest──▶ item store (stable IDs) ──list / done──▶ you
                                     │
                                     └─followup──▶ draft request ──/actiontrack-followup (Claude)──▶ Gmail Draft
```

## Install

You need Python 3.11 or newer. From this folder, run one command:

```bash
pip install -e .
```

To keep it in its own environment, use `pipx install .` or a venv:

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # Windows (bin/ on macOS/Linux)
```

## Commands

| Command | What it does |
|---|---|
| `actiontrack ingest <folder>` | Reads every `.md` note in the folder (subfolders are not read). It extracts the action items, works out owners and due dates, and merges duplicates. Then it prints a summary of skipped files, warnings and items that need attention. Running it again is safe: it adds nothing new and IDs never change. |
| `actiontrack list [--owner NAME] [--status open\|done\|overdue] [--due-before YYYY-MM-DD] [--json]` | Shows the items. Filters combine. Overdue items come first, marked `OVERDUE Nd`, and are shown in red in a terminal. |
| `actiontrack done <id>` | Marks an item as done. A later ingest never reopens it. |
| `actiontrack followup <owner> [--dry-run] [--json]` | Builds one email for the owner's open items, with overdue items first. `--dry-run` only prints it. Without `--dry-run` it saves a draft request to the outbox for the Claude skill below. |

**Options for every command:**
- `--store FILE`: where items are stored. The default is `$ACTIONTRACK_STORE` or `~/.actiontrack/store.json`.
- `--people FILE`: the people file. The default is `./people.yaml`, then `people.yaml` next to the store.

**`--owner` accepts:**
- a full name, in any case
- a first name, when only one person has it
- `unassigned`, `ambiguous` or `unknown`

**Exit codes:** `0` ok, `1` error (with a clear message), `2` invalid usage.

## Demo (the sample notes)

```bash
actiontrack ingest tests/fixtures/sample_notes
actiontrack list --status overdue
actiontrack list --owner "Priya Nair" --due-before 2026-10-20
actiontrack list --owner Priya              # error: matches Priya Nair and Priya Shah
actiontrack done 24
actiontrack followup "Priya Nair" --dry-run
```

To create the Gmail draft, open Claude Code in this folder (with the Gmail connector connected) and run:

```
/actiontrack-followup "Priya Nair"
```

The skill (`.claude/skills/actiontrack-followup/SKILL.md`) runs `actiontrack followup "<owner>" --json`. It then calls only the Gmail connector's `create_draft`, with the recipient, subject and body actiontrack produced. You review and send the draft from Gmail yourself.

`.claude/settings.json` denies the Gmail `send_message`, `reply` and `forward` tools. If your Gmail connector has a different server ID, update the three entries in that file.

Running `followup` twice creates two drafts.

## How notes are read

**Header.** Either of these works:
- `# Meeting: <title>`, then `Date:`, then `Attendees: A, B`
- YAML frontmatter with `title`, `date` and `attendees: [A, B]`

**Date formats:** `2026-09-01`, `9 September 2026` and `Monday, 14 September 2026`.

**What counts as an item:**
- Checkbox lines (`-`, `*` or `+`; `[ ]`, `[x]` or `[X]`), including nested ones
- `ACTION:` lines
- Rows of a table that has an Owner / Action / Due header

**Ignored:** lines in blockquotes, code blocks and `<!-- comments -->`, and plain sentences.

**Skipped, with the reason printed:**
- empty files
- binary or non-UTF-8 files
- files with no header
- files with an unparseable date (the date is never guessed)

**Other cases:**
- A note with no `Date:` line uses the date in its file name.
- A note with no attendees is still read, with a warning.

### Owners

Each owner is matched against **that meeting's** attendees.

| Written as | Result |
|---|---|
| `Priya`, when only one Priya attended | that Priya |
| `Priya N.` | the attending Priya whose surname starts with N |
| `@anita:` | Anita |
| `Anita & Rahul` | both people |
| `Lena (with Priya)` | Lena; Priya is noted in the task |
| `Priya`, when both Priyas attended | **ambiguous**; never guessed |
| `Someone`, `TBD` | **unassigned** |
| `Everyone`, `Team` | **unassigned** |
| A name not in the attendee list | looked up in `people.yaml` and the other notes; if not found, **unknown** |

Ambiguous, unassigned and unknown items appear in `list` and in the ingest summary. They are never put in a follow-up email.

### Due dates

Due dates are resolved from the **meeting date**, never from today.

| Phrase | Result |
|---|---|
| `by Friday` | the next Friday after the meeting. Written on a Friday, it means the Friday a week later. |
| `next Tuesday` | Tuesday of the following week |
| `tomorrow`, `EOD tomorrow` | the day after the meeting |
| `EOD` | the meeting day |
| `EOW` | the Friday of that week |
| `end of next week` | the Friday of the next week |
| `end of month` | the last day of the meeting's month |
| `mid-October` | 15 October |
| `10 Sep`, `Oct 3rd`, `Wed 16 Sep`, `results due 15 October`, `on 2026-10-14` | that date |
| `from 9 Oct`, `for Saturday 10 Oct`, `for November` | not a deadline; no due date |
| `before cutover` and other phrases it can't resolve | the phrase is kept and flagged as `unresolved` |

An item is **overdue** when it is not done and its due date is earlier than today. An item due today is not overdue.

### Duplicates

Two mentions count as the same item when both of these hold:
- They have the same owner. All unassigned items count as the same owner.
- Their task text is nearly identical after lowercasing and removing punctuation, small filler words and the due phrase. Nearly identical means at least 80% of the words match.

When duplicates merge:
- The latest mention sets the wording.
- The latest mention that gives a date sets the due date.
- A later `[x]` closes the item.

Related next steps, such as "draft the test plan" followed by "run the tests", stay as separate items.

## people.yaml

```yaml
people:
  - name: Priya Nair
    email: priya.nair@example.com
```

The addresses are placeholders, so edit them before you create real drafts. The people file is also used to work out owners for notes that have no attendee list.

## Tests

```bash
pytest -q
```

Tests cover each module and run end to end on a copy of the sample notes in `tests/fixtures/sample_notes`, with today fixed at 2026-10-15. They include every edge case: repeated and reworded items, missing owners or dates, shared first names, malformed notes, repeat ingests, and checks that no part of the code sends email.
