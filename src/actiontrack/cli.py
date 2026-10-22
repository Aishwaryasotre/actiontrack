"""actiontrack command line (spec sections 3-6)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import __version__
from .followup import PeopleFileError, build_draft, load_people, owners_with_work, write_drafts
from .ingest import ingest_folder
from .listing import select, source_label, status_of
from .people import Roster
from .store import connect, db_path, load_items, load_roster, save_all


def _date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid date '{s}', use YYYY-MM-DD")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="actiontrack", description="Track action items from meeting notes.")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--db", help="SQLite file (default .actiontrack/actiontrack.db or $ACTIONTRACK_DB)")
    p.add_argument("--as-of", type=_date, default=None, help="date used to judge 'overdue' (default: today)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ingest", help="parse a folder of .md notes")
    s.add_argument("folder")
    s.add_argument("-v", "--verbose", action="store_true", help="list every warning")

    s = sub.add_parser("list", help="show items")
    s.add_argument("--owner")
    s.add_argument("--status", choices=["open", "done", "overdue"])
    s.add_argument("--due-before", type=_date)
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("done", help="mark items done")
    s.add_argument("ids", nargs="+", type=int)

    s = sub.add_parser("assign", help="set the owner of an ambiguous/unassigned item")
    s.add_argument("id", type=int)
    s.add_argument("owner")

    s = sub.add_parser("followup", help="draft follow-up emails (never sends)")
    s.add_argument("owner", nargs="?")
    s.add_argument("--all", action="store_true")
    s.add_argument("--people", type=Path, default=Path("people.json"))
    s.add_argument("--out", type=Path, default=Path("drafts"))
    return p


def cmd_ingest(a, con) -> int:
    folder = Path(a.folder)
    if not folder.is_dir():
        print(f"error: folder not found: {folder}", file=sys.stderr)
        return 2
    res = ingest_folder(folder)
    save_all(con, res.items, res.roster)
    print(f"Ingested {folder}")
    print(f"  files seen   : {res.files_seen}")
    print(f"  parsed       : {len(res.parsed)}")
    print(f"  skipped      : {len(res.skipped)}")
    for f, why in res.skipped:
        print(f"      - {f}: {why}")
    print(f"  ignored      : {len(res.ignored)} (not .md)")
    for f in res.ignored:
        print(f"      - {f}")
    amb = sum(1 for i in res.items if i["owner_state"] == "ambiguous")
    un = sum(1 for i in res.items if i["owner_state"] in ("none", "group"))
    nodue = sum(1 for i in res.items if not i["due"] and not i["done"])
    dup = sum(1 for i in res.items if len(i["occurrences"]) > 1)
    print(f"  action lines : {res.occurrences} -> {len(res.items)} tracked items "
          f"({dup} merged across meetings)")
    print(f"  needs review : {amb} ambiguous owner, {un} unassigned/group, {nodue} open without due date")
    shown = res.warnings if a.verbose else res.warnings[:8]
    if res.warnings:
        print(f"  warnings     : {len(res.warnings)}")
        for w in shown:
            print(f"      - {w}")
        if len(shown) < len(res.warnings):
            print(f"      ... {len(res.warnings) - len(shown)} more (use -v)")
    return 0


def _src(r) -> str:
    name, extra = source_label(r)
    name = name.removesuffix(".md")
    return (name if len(name) <= 30 - len(extra) else name[: 29 - len(extra)] + "…") + extra


def cmd_list(a, con, as_of) -> int:
    rows = select(load_items(con), as_of, a.owner, a.status, a.due_before)
    if a.json:
        out = [{k: v for k, v in r.items() if k != "occurrences"}
               | {"sources": [f"{o['source']}:{o['line']}" for o in r["occurrences"]]} for r in rows]
        print(json.dumps(out, indent=2))
        return 0
    if not rows:
        print("No items.")
        return 0
    table = [("ID", "STATUS", "OWNER", "DUE", "TASK", "SOURCE")]
    for r in rows:
        st = r["status"] if r["status"] != "overdue" else f"overdue {r['days_overdue']}d"
        table.append((str(r["id"]), st, r["owner_label"], r["due"] or "-", r["task"], _src(r)))
    widths = [min(max(len(t[i]) for t in table), 58 if i == 4 else 30) for i in range(6)]
    for n, t in enumerate(table):
        print("  ".join((c if len(c) <= w else c[: w - 1] + "…").ljust(w) for c, w in zip(t, widths)).rstrip())
        if n == 0:
            print("  ".join("-" * w for w in widths))
    print(f"\n{len(rows)} item(s), as of {as_of.isoformat()}")
    return 0


def cmd_done(a, con) -> int:
    rc = 0
    items = {i["id"]: i for i in load_items(con)}
    for i in a.ids:
        it = items.get(i)
        if not it:
            print(f"error: no item with id {i}", file=sys.stderr)
            rc = 1
        elif it["done"]:
            print(f"#{i} already done: {it['task']}")
        else:
            with con:
                con.execute("UPDATE items SET manual_done=1 WHERE id=?", (i,))
            print(f"#{i} marked done: {it['task']}")
    return rc


def cmd_assign(a, con) -> int:
    roster = Roster()
    roster.names = load_roster(con)
    names = [n for n in roster.names if n.lower() == a.owner.strip().lower()]
    if not names:
        print(f"error: '{a.owner}' is not in the roster. Known: {', '.join(sorted(roster.names))}",
              file=sys.stderr)
        return 1
    if not con.execute("SELECT 1 FROM items WHERE id=?", (a.id,)).fetchone():
        print(f"error: no item with id {a.id}", file=sys.stderr)
        return 1
    with con:
        con.execute("UPDATE items SET owner_override=? WHERE id=?", (names[0], a.id))
    print(f"#{a.id} assigned to {names[0]}")
    return 0


def cmd_followup(a, con, as_of) -> int:
    items = load_items(con)
    work = owners_with_work(items, as_of)
    if a.all == bool(a.owner):
        print("error: give an owner or --all (not both)", file=sys.stderr)
        return 2
    if a.owner:
        roster = Roster()
        roster.names = load_roster(con)
        people = roster.find_person(a.owner)
        if not people:
            print(f"error: no person matches '{a.owner}'", file=sys.stderr)
            return 1
        if len(people) > 1:
            print(f"error: '{a.owner}' matches several people: {', '.join(people)}. "
                  "Use the full name.", file=sys.stderr)
            return 2
        targets = people
    else:
        targets = sorted(work)
    try:
        emails, people_warnings = load_people(a.people)
    except PeopleFileError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    for w in people_warnings:
        print(f"warning: {w}")
    drafts = []
    for name in targets:
        rows = work.get(name, [])
        if not rows:
            print(f"{name}: nothing open or overdue, no draft.")
            continue
        d = build_draft(name, rows, as_of, emails)
        drafts.append(d)
        warn = "" if d["to"] else "  [no email in people file]"
        print(f"{name}: draft with {len(d['item_ids'])} item(s){warn}")
    if drafts:
        write_drafts(drafts, a.out)
        print(f"\nWrote {len(drafts)} draft(s) to {a.out}/ (manifest.json, .json, .txt). Nothing was sent.")
        print("Next: create the Gmail drafts via the Gmail connector (see the actiontrack skill).")
    left = [i for i in items if not i["done"] and i["owner_state"] != "resolved"]
    if left:
        print(f"Left out of follow-ups: {len(left)} open item(s) without a resolved owner "
              "(`actiontrack list` then `actiontrack assign <id> \"Full Name\"`).")
    return 0


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    as_of = a.as_of or date.today()
    con = connect(db_path(a.db))
    try:
        return {"ingest": lambda: cmd_ingest(a, con),
                "list": lambda: cmd_list(a, con, as_of),
                "done": lambda: cmd_done(a, con),
                "assign": lambda: cmd_assign(a, con),
                "followup": lambda: cmd_followup(a, con, as_of)}[a.cmd]()
    except BrokenPipeError:  # NFR-04: e.g. `actiontrack list | head`
        import os
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
