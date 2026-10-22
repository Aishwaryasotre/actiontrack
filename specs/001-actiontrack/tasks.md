# Tasks 001: actiontrack

Order = spec first, tests next, code last. `[x]` = done.

- [x] T1 Read the original local notes and list parser edge cases (not included in the public repository)
- [x] T2 Write `spec.md` with requirement IDs and acceptance criteria
- [x] T3 `dates.py` + `tests/test_dates.py` (ING-03, ING-09)
- [x] T4 `people.py` + `tests/test_people.py` (ING-06..08)
- [x] T5 `parser.py`, `ingest.py`, `store.py` + `tests/test_ingest.py` (ING-01..05, 10..12)
- [x] T6 `listing.py`, `cli.py` list/done/assign + `tests/test_commands.py` (LST, DON, ASN)
- [x] T7 `followup.py` (FUP) + draft manifest
- [x] T8 `tests/test_sample.py`: acceptance on the synthetic fixture set
- [x] T9 `scripts/check_spec_coverage.py`
- [x] T10 Skill `.claude/skills/actiontrack/SKILL.md`, `CLAUDE.md`, `README.md`
- [x] T11a (LIVE) Gmail workflow verification completed; live evidence is intentionally excluded from the public repository.
- [ ] T11b (NOT VERIFIED) run the skill end to end to create a draft with a real recipient and test the duplicate check against the real `list_drafts` shape. Needs explicit approval for one new draft and real addresses
- [x] T13 Final QA review: fixed loose owner matching (LST-02, FUP-01), `##` title bug (ING-02), strict spec-coverage guard
- [x] T14 (AUTO) mock-connector contract tests, SKILL.md static checks, people-file validation (FUP-04 defect fixed)
- [ ] T12 Real `people.json` with team emails (not committed)
