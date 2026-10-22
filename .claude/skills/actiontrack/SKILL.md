---
name: actiontrack
description: Track action items from markdown meeting notes and draft follow-up emails as Gmail drafts. Use when the user wants to ingest meeting notes, see open or overdue action items, mark items done, or follow up with owners. Never sends email.
---

# actiontrack

Operate the `actiontrack` CLI in this repo (`python3 -m actiontrack`, with `PYTHONPATH=src`, or the installed
`actiontrack`). Spec: `specs/001-actiontrack/spec.md`. Hard rule: **create Gmail drafts only; never send.**

## 1. Ingest

```bash
actiontrack ingest <notes-folder>
```

Read the report back to the user: parsed / skipped (with reasons) / ignored, merged duplicates, and
"needs review" counts. Skipped notes are expected for malformed files; do not try to repair them.
Ingest is safe to re-run; `done` and `assign` decisions survive.

## 2. Answer questions

Use `list` with `--owner`, `--status open|done|overdue`, `--due-before YYYY-MM-DD`, and `--json` when you need
to process the output. Pass `--as-of <date>` (before the subcommand) when the user wants "as of" a date.
`open` excludes overdue. Items shown as `Name (?)` are ambiguous (same first name); `(unassigned)` and `(group)`
have no single owner.

## 3. Resolve ambiguity before follow-ups

For each `(?)` item, ask the user who it is (offer the candidates from the ingest warning), then
`actiontrack assign <id> "Full Name"`. Never pick for them. Mark finished work with `actiontrack done <id> ...`.

## 4. Follow-up drafts

1. `actiontrack followup --all` (or `followup "<Full Name>"`; a shared first name exits 2 listing the candidates).
   Add `--people people.json` for recipient emails.
2. Read `drafts/manifest.json` and each `drafts/<slug>.json`. Show the user a short preview per draft
   (to, subject, counts) and mention owners with no email and the "left out" count.
3. **Ask for confirmation** before creating anything in Gmail.
4. Load the Gmail tools with ToolSearch (`select:mcp__Gmail__create_draft,mcp__Gmail__list_drafts`).
   - **Duplicate check first (read-only):** `mcp__Gmail__list_drafts` with `query: "subject:Follow-up"` and
     `view: DRAFT_VIEW_FULL`. If a draft with the same subject and recipient already exists, tell the user and skip it
     unless they ask for a replacement. Re-running `followup` never removes earlier Gmail drafts.
   - Call **`mcp__Gmail__create_draft`** once per manifest entry: `to` is an **array** (`[]` or omitted when the
     JSON `to` is empty, and say so), `subject` and `body` copied unchanged from `drafts/<slug>.json`.
     `body` is plain text (no Markdown); leave `htmlBody`, `cc`, `bcc` and `attachments` unset.
   - **Forbidden Gmail tools, always:** `send_message`, `reply`, `forward`, and also `update_draft`,
     `delete_draft`, `trash_*`, label or spam tools. Even if the user says "just send them", say you only create
     drafts and they can send from Gmail. Deleting a draft needs the user's explicit request.
   - If the Gmail tools are not available (connector off or not connected), say so, tell the user to enable the Gmail
     connector for this chat, and leave the previews in `drafts/`. Do not fall back to any other mail method.
5. Report which drafts were created (owner, subject) and that nothing was sent.

## Do not

- Edit the original local notes in `samples/notes/` or place real meeting content in `samples/synthetic-notes/`.
  Invent email addresses. Email ambiguous or group items. Send anything.
- Run `ingest` on a different folder without warning the user it replaces the tracked set (see README).
