# actiontrack

Meeting notes pile up as markdown. Action items get lost and follow-ups are late.
`actiontrack` reads the notes, tracks each action item once, and drafts (never sends) follow-up emails.

```bash
pip install -e .            # or: export PYTHONPATH=src and use python3 -m actiontrack
actiontrack ingest samples/synthetic-notes/    # parse the synthetic fixtures
actiontrack list                               # everything, overdue first
actiontrack list --owner priya --status overdue --due-before 2026-11-01
actiontrack done 12 14
actiontrack assign 27 "Priya Shah"             # fix an ambiguous owner
actiontrack followup "Sam Okafor"              # or --all; writes drafts/ + manifest.json
```

`--as-of 2026-10-22` pins the "today" used for overdue. It is a global flag and must come **before** the subcommand (`actiontrack --as-of 2026-10-22 list`). Owner arguments match a full name or a whole first name / surname, never a fragment.

## What it handles

| Case | Behaviour |
|------|-----------|
| Same task in several meetings | One item, all sources kept, latest status/due wins |
| No owner / "Everyone" / "TBD" | Stored, shown as `(unassigned)` / `(group)`, never emailed |
| Two Priyas, two Rahuls | Resolved by the meeting's attendees, else `Priya (?)` until you `assign` |
| `by Friday`, `EOD tomorrow`, `next Tuesday`, `mid-October`, `9 Oct` | Resolved to a date relative to the **meeting** date |
| Empty, binary, undated notes | Skipped and listed in the ingest report; run continues |
| Quoted, code-fenced, commented-out checkboxes | Ignored |
| Front matter notes, `ACTION:` lines, tables, `*` / `+` bullets, nesting | Parsed |

`ingest` mirrors the folder you give it: items that no longer appear in any note are removed, except ones you changed
with `done` or `assign`. Ingesting a second, different folder therefore replaces the first folder's items. Use one
notes folder per database (`--db`).

"Overdue" means no note has ticked the item off yet. If people finish work without updating the notes, expect many
overdue items. The draft asks owners to confirm, and you can close items with `done`.

Status is `done`, `overdue` (not done and due before as-of) or `open`; `--status open` excludes overdue.

## Follow-up emails and Gmail

`followup` writes `drafts/<name>.json|.txt` and `drafts/manifest.json` (`"send": false`). It has no send code.
To put them in Gmail, ask Claude: *"use the actiontrack skill to create the Gmail drafts"*. It previews them,
waits for your OK, and creates **drafts only** through the Gmail connector. Put recipient addresses in
the git-ignored `people.json`, for example `{"Alex Example": "alex@example.invalid"}`. The sample address is not deliverable.

The repository's Gmail contract tests use a mock connector. No live Gmail evidence is included.

## Development

Spec-driven: see `CLAUDE.md` and `specs/001-actiontrack/` (`spec.md`, `plan.md`, `tasks.md`).

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -t .
python3 scripts/check_spec_coverage.py
```
