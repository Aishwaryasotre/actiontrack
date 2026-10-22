# CLAUDE.md: actiontrack

CLI that turns markdown meeting notes into tracked action items and draft follow-up emails.
Python 3.10+, standard library only. Spec-driven: **`specs/001-actiontrack/spec.md` is the source of truth.**

## Workflow (spec-driven)

1. Behaviour change? Edit `spec.md` first (add or change a requirement ID).
2. Add or change a test whose name contains the ID (e.g. `test_overdue_LST_03`).
3. Then change code. Run:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -t .
python3 scripts/check_spec_coverage.py     # every spec ID must be referenced by a test
```

Never change code to make a test pass without checking the spec says that is correct.

## Commands

```bash
export PYTHONPATH=src            # or: pip install -e .
python3 -m actiontrack ingest samples/synthetic-notes
python3 -m actiontrack list --status overdue
python3 -m actiontrack done 12
python3 -m actiontrack assign 27 "Priya Shah"
python3 -m actiontrack followup "Sam Okafor" --people people.json   # or --all
```

Global flags go before the subcommand: `--db FILE`, `--as-of YYYY-MM-DD`.

## Layout

`src/actiontrack/` dates, people, parser, ingest, store, listing, followup, cli.
`tests/` mirrors the spec. `samples/synthetic-notes/` contains clearly synthetic parser fixtures. The original local
meeting notes in `samples/notes/` are excluded from version control and must not be modified or committed.
`.claude/skills/actiontrack/SKILL.md` is the workflow that creates Gmail drafts.

## Hard rules

- **Never send email.** Only create drafts. Do not add smtplib, a send API, or any send code (a test greps for this).
- **Never guess an owner.** Ambiguous first names stay `ambiguous` until `assign`. They are never emailed.
- One malformed note must never abort an ingest. Skip, report, continue.
- Due dates resolve against the meeting date, not today.
- Real team emails belong in `people.json`, which is git-ignored. Public examples use reserved `.invalid` addresses.
- Tests must be deterministic: always pass `--as-of`.
