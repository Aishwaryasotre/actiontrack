# Plan 001: actiontrack

Implements `spec.md`. Python 3.10+, stdlib only.

## Architecture

```
notes/*.md ──► parser.py ──► ingest.py ──► store.py (SQLite) ──► listing.py ──► cli.py
                 │  dates.py (due phrases)       ▲                   │
                 └─ people.py (owners, roster) ──┘                   └──► followup.py ──► drafts/*.json + manifest.json
                                                                                              │
                                                              actiontrack skill + Gmail MCP ◄─┘  (create DRAFT only)
```

| Module | Responsibility | Spec |
|--------|----------------|------|
| `dates.py` | header dates, due-phrase extraction relative to the meeting date | ING-03, ING-09 |
| `people.py` | owner syntax, roster, first-name disambiguation | ING-06..08 |
| `parser.py` | one note: metadata, action lines, skip rules (fences, comments, quotes), `SkipNote` | ING-02..05, ING-11 |
| `ingest.py` | two passes (roster, then items), merge duplicates, build report | ING-01, ING-10, ING-11 |
| `store.py` | SQLite schema, idempotent upsert keyed on `owner|normalised task`, manual overrides | ING-12, NFR-02 |
| `listing.py` | status, filters, ordering | LST-* |
| `followup.py` | draft text, manifest, people.json | FUP-* |
| `cli.py` | argparse wiring and output | all |

## Key decisions

1. **Two-pass ingest.** The roster needs every note's attendees before any first name can be resolved,
   so unique-first-name resolution works even in notes with no attendee list.
2. **Never guess an owner.** Two Priyas / two Rahuls with no way to tell them apart gives state
   `ambiguous`, visible in `list`, excluded from follow-ups, fixed with `assign`. A wrong email is worse than a missing one.
3. **Dedup key = owner + normalised task, not due date.** Wording and deadlines drift between
   meetings ("by Friday" then "by tomorrow"), the commitment does not. Latest occurrence wins for status and due.
4. **Due dates resolve against the meeting date**, so ingesting the same note next month gives the same date.
   `--as-of` only affects overdue judgement.
5. **Manual state outlives re-ingest.** `done` and `assign` are stored beside, not inside, the parsed
   data, so re-running ingest after notes change never loses a human decision.
6. **The CLI cannot call MCP.** `followup` writes a manifest of review-ready drafts. The skill performs
   the Gmail step with the connector's create-draft tool. This keeps "never sends" structurally true: there is
   no send code in the repo (enforced by `test_never_sends_FUP_03`), and the skill forbids send tools.
7. **Tests mirror the spec.** Test names carry requirement IDs. `scripts/check_spec_coverage.py` fails when an ID has no test.

## Known limits (deliberately out of scope)

- `for Saturday 10 Oct` and `from 9 Oct` are not treated as due dates (no marker word).
- Free-text commitments without a checkbox / `ACTION:` / table row are not extracted.
- Two owners with the same full name cannot be told apart.
- Trailing words after a removed due phrase can remain in the task text (`..., results`).
- `ingest` replaces the tracked set with the folder's contents (ING-12). One notes folder per database.
- "Overdue" only means "never ticked in a note"; work finished without a note update still shows as overdue.
- `--as-of` is a global flag and must precede the subcommand.
- Verified on Python 3.11, 3.12, 3.13. The declared minimum 3.10 was not available to test.
- Re-running `followup` + the skill can create duplicate Gmail drafts; the skill checks `list_drafts` first.

## Verification of the Gmail step (GML-01 / GML-02)

Full report with evidence: `qa/gmail-verification.md`. Evidence types are kept separate there:

- **AUTO**: `tests/test_gmail_contract.py` (mock connector, test double of the skill, static check of SKILL.md). It does not exercise the real skill.
- **SRC**: the CLI has no Gmail code; Gmail operations exist only in SKILL.md (create_draft, list_drafts; send paths forbidden).
- **LIVE**: the existing test draft was read back through the connector (label DRAFT only, empty recipient, body equal to generator output). Sent search empty.
- **NOT VERIFIED**: skill end-to-end run, draft with a real recipient, duplicate check against the real `list_drafts` shape.

Procedure to complete the NOT VERIFIED items (needs the user's approval for one new draft): put real addresses in
`people.json`, run `actiontrack followup "<Full Name>"`, ask Claude to use the `actiontrack` skill, confirm the preview,
then read the draft back with `get_draft` and check label `DRAFT`, subject, `to`, body.
