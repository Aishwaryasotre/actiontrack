"""Ingest a folder of notes into merged items (spec ING-01..ING-12)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .dates import ISO_RE, extract_due, parse_due_at_start
from .parser import Note, SkipNote, normalise_task, parse_note, read_text
from .people import Roster, split_owner


@dataclass
class IngestResult:
    files_seen: int = 0
    ignored: list[str] = field(default_factory=list)
    parsed: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    occurrences: int = 0
    items: list[dict] = field(default_factory=list)
    roster: set[str] = field(default_factory=set)


def scan(folder: Path) -> tuple[list[Path], list[Path]]:
    files = sorted(p for p in folder.rglob("*") if p.is_file())
    md = [p for p in files if p.suffix.lower() == ".md"]
    other = [p for p in files if p.suffix.lower() != ".md"]
    return md, other


def ingest_folder(folder: Path) -> IngestResult:
    res = IngestResult()
    md, other = scan(folder)
    res.files_seen = len(md) + len(other)
    res.ignored = [str(p.relative_to(folder)) for p in other]

    notes: list[Note] = []
    for p in md:
        rel = str(p.relative_to(folder))
        try:
            note = parse_note(p)
            note.path = rel
            notes.append(note)
            res.parsed.append(rel)
            res.warnings += [f"{rel}: {w}" for w in note.warnings]
        except SkipNote as e:
            res.skipped.append((rel, str(e)))
        except Exception as e:  # ING-11: one bad note never stops the run
            res.skipped.append((rel, f"unexpected error: {type(e).__name__}: {e}"))

    roster = Roster()
    for n in notes:
        roster.add(n.attendees)
    res.roster = set(roster.names)

    merged: dict[str, dict] = {}
    for note in sorted(notes, key=lambda n: (n.date, n.path)):
        for raw in note.items:
            res.occurrences += 1
            for rec in _records(note, raw, roster, res):
                it = merged.setdefault(rec["key"], {**{k: rec[k] for k in (
                    "key", "owner", "owner_state", "owner_raw", "candidates")}, "occurrences": []})
                it["occurrences"].append(rec["occ"])
                it["task"] = rec["task"]
                if rec["due"]:
                    it["due"], it["due_raw"] = rec["due"], rec["due_raw"]
    for it in merged.values():
        it.setdefault("due", None)
        it.setdefault("due_raw", None)
        occ = it["occurrences"]
        it["done"] = bool(occ[-1]["checked"])
        if it["done"] is False and any(o["checked"] for o in occ[:-1]):
            res.warnings.append(
                f"reopened: '{it['task']}' was checked off in an earlier note but appears "
                f"open again in {occ[-1]['source']}")
        if it["owner_state"] == "ambiguous":
            res.warnings.append(
                f"ambiguous owner '{it['owner_raw']}' ({', '.join(it['candidates'])}) for "
                f"'{it['task']}' ({occ[-1]['source']}); use `actiontrack assign`")
    res.items = list(merged.values())  # insertion order = first appearance, so ids follow the notes
    return res


def _records(note: Note, raw, roster: Roster, res: IngestResult):
    if raw.kind == "table":
        owners_raw, task = [raw.table_owner], raw.text
    else:
        owners_raw, task = split_owner(raw.text)
    table_due = None
    if raw.kind == "table" and raw.table_due:
        table_due = parse_due_at_start(raw.table_due, note.date)[0]
        if table_due is None:
            res.warnings.append(f"{note.path}:{raw.line}: could not read due '{raw.table_due}'")
    task, due, due_raw, unresolved = extract_due(task, note.date)
    if table_due:
        due, due_raw = table_due, raw.table_due
    if unresolved and not due:
        res.warnings.append(f"{note.path}:{raw.line}: could not resolve due phrase in '{raw.text}'")
    norm = normalise_task(task)
    occ_base = {"source": note.path, "line": raw.line, "meeting_date": note.date.isoformat(),
                "meeting_title": note.title, "checked": raw.checked, "raw": raw.text}
    if not owners_raw:
        owners_raw = [""]
    for o in owners_raw:
        if o:
            ow = roster.resolve(o, note.attendees)
        else:
            from .people import Owner
            ow = Owner("none", None, "")
        if ow.state == "resolved":
            who = ow.name.lower()
        elif ow.state == "ambiguous":
            who = f"?{ow.raw.lower()}"
        else:
            who = f"({ow.state})"
        yield {"key": f"{who}|{norm}", "owner": ow.name if ow.state == "resolved" else None,
               "owner_state": ow.state, "owner_raw": ow.raw, "candidates": ow.candidates,
               "task": task, "due": due.isoformat() if due else None, "due_raw": due_raw,
               "occ": dict(occ_base)}
