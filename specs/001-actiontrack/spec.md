# Spec 001: actiontrack

Status: approved for implementation. Every requirement has an ID. Every ID must be
referenced by at least one test (`scripts/check_spec_coverage.py` enforces this).
Change the spec first, then the tests, then the code.

## 1. Purpose

Meeting notes are markdown files. Action items get lost and follow-ups are late.
`actiontrack` reads a folder of notes, keeps one tracked record per real action item,
and drafts (never sends) one follow-up email per owner.

## 2. Vocabulary

- **Note**: one `.md` file. **Occurrence**: one action line in one note.
- **Item**: one tracked task. Several occurrences can map to one item (duplicates).
- **As-of date**: the date "overdue" is judged against. Default today, override `--as-of YYYY-MM-DD`.
- **Roster**: every full name seen in any `Attendees` field across all parsed notes.

## 3. Ingest: `actiontrack ingest <folder>`

| ID | Requirement |
|----|-------------|
| ING-01 | Scan `<folder>` recursively in sorted order. Parse `*.md` only. Other files are counted as "ignored", not errors. A missing folder exits 2 with a message. |
| ING-02 | Meeting metadata comes from `Date:` / `Attendees:` lines (comma separated) or from YAML front matter (`date:`, `attendees: [a, b]`). Title comes from `# Meeting: X` / `# X` (single `#` only; `##` sections never count), front matter `title:`, or the filename. |
| ING-03 | Dates accept `2026-09-01`, `9 September 2026`, `Monday, 14 September 2026`. If the header date is missing or unparseable but the filename starts with `YYYY-MM-DD`, use the filename date and emit a warning. If neither works the note is skipped. |
| ING-04 | An action line is a list bullet (`-`, `*`, `+`, any indentation, so nested works) followed by `[ ]` (open) or `[x]`/`[X]` (done). Also recognised: lines starting `ACTION:` (open) and markdown table rows under an `Owner / Action|Task / Due` header (open). Action lines may sit anywhere in the note, not only under an "Action items" heading. |
| ING-05 | Never extract from fenced code blocks, HTML comments (single or multi line) or blockquote (`>`) lines. |
| ING-06 | Owner forms: `Name to <task>`, `@name: <task>`, `Name: <task>`, `A & B to <task>` / `A and B` / `A, B` (one item per owner), `Name (with Other) to <task>` (owner = Name, the "(with Other)" remark stays in the task text), initials like `Priya N.`. |
| ING-07 | **Same first name.** Resolve a name against the meeting's attendees first, then against the roster. Exactly one candidate means resolved to that full name. A surname or initial narrows candidates. More than one candidate means state `ambiguous` and the item is never assigned to anyone silently. Zero candidates means the name is kept as written. |
| ING-08 | `Everyone`, `Team`, `All` mean state `group`. `Someone`, `TBD`, `Nobody`, or no recognisable owner mean state `none`. Items with state group, none or ambiguous are stored, shown by `list` as `(group)`, `(unassigned)`, `Priya (?)`, and excluded from follow-ups, which report how many were left out. |
| ING-09 | Due dates are resolved against the **meeting date** (never against today). Only phrases after a marker word (`by`, `due`, `before`, `until`, `on`) count. Forms: ISO; `9 Oct`, `Oct 3rd`, `15 October`, `Wed 16 Sep`; `today`, `EOD`, `tomorrow`, `EOD tomorrow`; weekday names and abbreviations; `next <weekday>`; `end of month`; `end of (next) week` (Friday); `mid-October` (15th). A bare weekday means the first such day **strictly after** the meeting date. `next <weekday>` means that weekday in the following Monday-to-Sunday week. Day-month with no year uses the meeting year, rolling forward a year if it would land more than 60 days before the meeting. A marker followed by something that is not a date (`by 10%`) is ignored. No due phrase means due is null. The raw phrase is always kept. A due phrase that cannot be resolved gives null plus a warning. |
| ING-10 | **Duplicates.** Items merge when owner (resolved full name, or raw name when not resolved) and normalised task text match. Normalisation lowercases, drops articles (`the a an`), the due phrase and punctuation, collapses spaces. A merged item keeps every occurrence (file, line, meeting date). Status: the chronologically latest occurrence wins (a later `[x]` means done, a later `[ ]` after a `[x]` reopens it and warns). Due: the latest occurrence that has a due date. |
| ING-11 | **Malformed notes are skipped and reported, never fatal.** Empty file, binary or non-UTF-8 content, no usable date. Any unexpected error inside one note skips that note. The run ends with a report: parsed / skipped (with reason per file) / ignored / items / warnings, and exits 0. |
| ING-12 | Re-running ingest is idempotent: same ids, no duplicate rows. Manual changes (`done`, `assign`) survive re-ingest. Items that no longer appear in any note and have no manual change are removed. |

## 4. List: `actiontrack list`

| ID | Requirement |
|----|-------------|
| LST-01 | Shows id, status, owner, due, task, source (latest note, plus `+N` when it appears in more notes). Empty result prints `No items.`. |
| LST-02 | Filters, combinable (AND): `--owner <text>` (case-insensitive; matches the full name, or a whole first name or surname word; fragments such as `ok` or `an` never match; ambiguous items match only when the query equals their raw name, e.g. `Priya`), `--status open|done|overdue`, `--due-before <YYYY-MM-DD>` (strictly before, items without a due date never match). |
| LST-03 | Status is exactly one of `done`, `overdue` (not done and due < as-of), `open` (not done, no due date or due >= as-of). `--status open` therefore excludes overdue. Overdue rows show days late. |
| LST-04 | `--json` prints a JSON array with all fields for scripting. |
| LST-05 | Order: overdue first (most late first), then open by due date (no-due last), then done. Ties by id. |

## 5. Done / assign

| ID | Requirement |
|----|-------------|
| DON-01 | `actiontrack done <id> [<id>...]` marks items done. Unknown id: message and exit 1 (other ids in the call still processed). Already done: reported, exit 0. |
| ASN-01 | `actiontrack assign <id> "<Full Name>"` sets the owner of an ambiguous / unassigned item. The name must be in the roster, else exit 1. |

## 6. Follow-up: `actiontrack followup <owner> | --all`

| ID | Requirement |
|----|-------------|
| FUP-01 | `<owner>` must identify exactly one person: full name, or a whole first-name / surname word (never a fragment, so a typo cannot select someone). A first name shared by several people exits 2 listing the candidates. Unknown person exits 1. `--all` drafts for every resolved owner who has at least one open or overdue item. |
| FUP-02 | One draft per owner containing their overdue items (with days late) and open items (with due date or `no due date`), each with the meeting/date it came from. Done items are excluded. |
| FUP-03 | **Never sends.** The tool has no send code path. It writes `drafts/<owner-slug>.json` (to, subject, body, owner, item ids), `drafts/<owner-slug>.txt` (human preview) and `drafts/manifest.json` (`"send": false`, status `pending_gmail_draft`). Creating the Gmail draft is done through the Gmail MCP connector by the skill, see section 7. |
| FUP-04 | Recipient email comes from a `people.json` (`{"Full Name": "email"}`, via `--people`, default `./people.json`), matched on the exact full name (case-insensitive, never a first name or fragment). Missing person, missing file, `null`, or a value that is not exactly one plain address (`a@b.c`; no spaces, commas, semicolons, angle brackets or line breaks) gives an empty `to`: the draft is still produced, with a warning. A people file that is not valid JSON or not a JSON object exits 2 with a one-line error and writes no drafts. A recipient is never guessed. |
| FUP-05 | Owner with nothing open or overdue: no draft, message says so, exit 0. |
| FUP-06 | The command prints how many unassigned / group / ambiguous items were left out. |

## 7. Gmail connector (skill-level)

The CLI contains **no Gmail code**. It only writes the manifest. All Gmail operations are instructions in
`.claude/skills/actiontrack/SKILL.md`. GML-01 is therefore verified by (a) a static check of SKILL.md and (b) a
mock connector that plays the skill's procedure; the real skill is executed by Claude and cannot be unit tested.

| ID | Requirement |
|----|-------------|
| GML-01 | The skill creates drafts only through the Gmail MCP **create draft** tool, one per manifest entry, and never calls any send tool. It shows the user the drafts and waits for confirmation before creating them. If the Gmail connector is not available it says so and leaves the previews in `drafts/`. |
| GML-02 | **Live check (manual, evidence required).** A draft created by the skill can be retrieved through the Gmail connector with label `DRAFT` only, the manifest subject, the manifest body, and no recipient when `to` is empty. Evidence lives in `specs/001-actiontrack/qa/`. |

## 8. Non-functional

| ID | Requirement |
|----|-------------|
| NFR-01 | Python 3.10+, standard library only. |
| NFR-02 | State lives in one SQLite file (`.actiontrack/actiontrack.db`, override `--db` or `ACTIONTRACK_DB`). |
| NFR-03 | Deterministic: same notes and as-of date give identical output. |
| NFR-04 | A closed output pipe (`actiontrack list | head`) ends quietly with no traceback. |

## 9. Acceptance on the synthetic fixture (`samples/synthetic-notes`)

Used by `tests/test_sample.py`.

1. Six synthetic Markdown notes parse successfully; malformed and binary-note behavior is covered with temporary fixtures in `test_ingest.py`.
2. `2026-10-03-example-pipeline.md` is parsed using the filename date, with a warning.
3. Quoted, commented-out, and code-fenced synthetic checkboxes are not extracted.
4. The workshop note exercises a table row, an `ACTION:` line, a nested item, and `*` / `+` bullets.
5. Repeated first names with attendee context, and a note without attendees, produce ambiguous owners; full names resolve.
6. The "revised proposal to ExampleCo" item is merged across three occurrences and retains its completed status.
7. `Everyone`, `TBD`, and `Someone` owners remain group or unassigned.
8. `Casey Demo to freeze fixture edits from 9 Oct` has no due date (`from` is not a due marker).
