"""Status computation, filtering and ordering (spec LST-01..LST-05)."""
from __future__ import annotations

from datetime import date


def status_of(item: dict, as_of: date) -> tuple[str, int]:
    """Return (done|overdue|open, days_overdue)."""
    if item["done"]:
        return "done", 0
    if item["due"]:
        due = date.fromisoformat(item["due"])
        if due < as_of:
            return "overdue", (as_of - due).days
    return "open", 0


def owner_label(item: dict) -> str:
    st = item["owner_state"]
    if st == "resolved":
        return item["owner"]
    if st == "ambiguous":
        return f"{item['owner_raw']} (?)"
    return "(group)" if st == "group" else "(unassigned)"


def owner_matches(item: dict, query: str) -> bool:
    q = query.strip().lower()
    if item["owner_state"] == "resolved":
        name = item["owner"].lower()
        return q != "" and (name == q or q in name.split())
    if item["owner_state"] == "ambiguous":
        return q != "" and item["owner_raw"].lower().strip(".") == q
    return False


def select(items: list[dict], as_of: date, owner=None, status=None, due_before=None) -> list[dict]:
    rows = []
    for it in items:
        st, late = status_of(it, as_of)
        if status and st != status:
            continue
        if owner and not owner_matches(it, owner):
            continue
        if due_before and not (it["due"] and date.fromisoformat(it["due"]) < due_before):
            continue
        rows.append({**it, "status": st, "days_overdue": late, "owner_label": owner_label(it)})
    rank = {"overdue": 0, "open": 1, "done": 2}

    def key(r):
        if r["status"] == "overdue":
            return (0, -r["days_overdue"], r["id"])
        if r["status"] == "open":
            return (1, r["due"] or "9999-12-31", r["id"])
        return (2, "", r["id"])

    return sorted(rows, key=key)


def source_label(item: dict) -> tuple[str, str]:
    occ = item["occurrences"]
    last = occ[-1]
    extra = f" +{len(occ) - 1}" if len(occ) > 1 else ""
    return last["source"], extra
