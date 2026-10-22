"""SQLite persistence (spec NFR-02, ING-12)."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT NOT NULL UNIQUE,
  owner TEXT,                 -- resolved full name, or NULL
  owner_state TEXT NOT NULL,  -- resolved | ambiguous | group | none
  owner_raw TEXT,
  candidates TEXT,            -- JSON list for ambiguous owners
  task TEXT NOT NULL,
  due TEXT,                   -- ISO date or NULL
  due_raw TEXT,
  derived_done INTEGER NOT NULL,
  manual_done INTEGER NOT NULL DEFAULT 0,
  owner_override TEXT
);
CREATE TABLE IF NOT EXISTS occurrences (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  source TEXT NOT NULL,
  line INTEGER NOT NULL,
  meeting_date TEXT NOT NULL,
  meeting_title TEXT NOT NULL,
  checked INTEGER NOT NULL,
  raw TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS roster (name TEXT PRIMARY KEY);
"""


def db_path(arg: str | None) -> Path:
    return Path(arg or os.environ.get("ACTIONTRACK_DB") or ".actiontrack/actiontrack.db")


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA)
    return con


def save_all(con: sqlite3.Connection, merged: list[dict], roster: set[str]) -> None:
    """Replace occurrences, upsert items by key, keep manual changes and ids."""
    with con:
        existing = {r["key"]: r["id"] for r in con.execute("SELECT id, key FROM items")}
        con.execute("DELETE FROM occurrences")
        seen = set()
        for it in merged:
            seen.add(it["key"])
            vals = (it["owner"], it["owner_state"], it["owner_raw"],
                    json.dumps(it["candidates"]), it["task"], it["due"], it["due_raw"],
                    int(it["done"]))
            if it["key"] in existing:
                item_id = existing[it["key"]]
                con.execute(
                    "UPDATE items SET owner=?, owner_state=?, owner_raw=?, candidates=?, task=?,"
                    " due=?, due_raw=?, derived_done=? WHERE id=?", vals + (item_id,))
            else:
                item_id = con.execute(
                    "INSERT INTO items(owner, owner_state, owner_raw, candidates, task, due,"
                    " due_raw, derived_done, key) VALUES (?,?,?,?,?,?,?,?,?)",
                    vals + (it["key"],)).lastrowid
            for o in it["occurrences"]:
                con.execute(
                    "INSERT INTO occurrences(item_id, source, line, meeting_date, meeting_title,"
                    " checked, raw) VALUES (?,?,?,?,?,?,?)",
                    (item_id, o["source"], o["line"], o["meeting_date"], o["meeting_title"],
                     int(o["checked"]), o["raw"]))
        for key, item_id in existing.items():
            if key in seen:
                continue
            row = con.execute("SELECT manual_done, owner_override FROM items WHERE id=?",
                              (item_id,)).fetchone()
            if not row["manual_done"] and not row["owner_override"]:
                con.execute("DELETE FROM items WHERE id=?", (item_id,))
        con.execute("DELETE FROM roster")
        con.executemany("INSERT INTO roster(name) VALUES (?)", [(n,) for n in sorted(roster)])


def load_items(con: sqlite3.Connection) -> list[dict]:
    items = []
    for r in con.execute("SELECT * FROM items ORDER BY id"):
        d = dict(r)
        d["candidates"] = json.loads(d["candidates"] or "[]")
        if d["owner_override"]:
            d["owner"], d["owner_state"] = d["owner_override"], "resolved"
        d["done"] = bool(d["derived_done"] or d["manual_done"])
        d["occurrences"] = [dict(o) for o in con.execute(
            "SELECT * FROM occurrences WHERE item_id=? ORDER BY meeting_date, source, line",
            (d["id"],))]
        items.append(d)
    return items


def load_roster(con: sqlite3.Connection) -> set[str]:
    return {r["name"] for r in con.execute("SELECT name FROM roster")}
