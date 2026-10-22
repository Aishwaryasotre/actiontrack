"""Draft follow-up emails per owner (spec FUP-01..FUP-06). Never sends."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from .listing import select


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class PeopleFileError(ValueError):
    """people.json exists but cannot be used (not JSON, or not an object)."""


_EMAIL_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")


def load_people(path: Path | None) -> tuple[dict[str, str], list[str]]:
    """Return ({lowercase full name: email}, warnings). Never guesses: unusable values are dropped (FUP-04)."""
    if not path or not path.exists():
        return {}, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        raise PeopleFileError(f"people file {path} is not valid JSON ({e})") from None
    if not isinstance(data, dict):
        raise PeopleFileError(f"people file {path} must be a JSON object of \"Full Name\": \"email\"")
    emails, warnings = {}, []
    for name, value in data.items():
        if isinstance(value, str) and _EMAIL_RE.match(value.strip()):
            emails[str(name).lower()] = value.strip()
        else:
            warnings.append(f"invalid email for {name} in {path.name}, ignored (draft will have no recipient)")
    return emails, warnings


def build_draft(owner: str, rows: list[dict], as_of: date, emails: dict[str, str]) -> dict:
    overdue = [r for r in rows if r["status"] == "overdue"]
    openr = [r for r in rows if r["status"] == "open"]
    first = owner.split()[0]

    def src(r):
        o = r["occurrences"][0]
        return f"{o['meeting_title']}, {o['meeting_date']}"

    lines = [f"Hi {first},", "",
             "A quick follow-up on action items from recent meetings that are still open "
             f"(as of {as_of.isoformat()}).", ""]
    if overdue:
        lines.append(f"Overdue ({len(overdue)}):")
        for r in overdue:
            lines.append(f"  - {r['task']} - was due {r['due']} ({r['days_overdue']} days late) "
                         f"[{src(r)}]")
        lines.append("")
    if openr:
        lines.append(f"Open ({len(openr)}):")
        for r in openr:
            due = f"due {r['due']}" if r["due"] else "no due date"
            lines.append(f"  - {r['task']} - {due} [{src(r)}]")
        lines.append("")
    lines += ["Could you reply with a status or a new date for each? If something is already "
              "done or no longer needed, just tell me and I'll close it.", "", "Thanks!"]
    total = len(overdue) + len(openr)
    subject = (f"Follow-up: {total} open action item{'s' if total != 1 else ''}"
               f"{f' ({len(overdue)} overdue)' if overdue else ''}")
    return {"owner": owner, "to": emails.get(owner.lower(), ""), "subject": subject,
            "body": "\n".join(lines), "item_ids": [r["id"] for r in overdue + openr],
            "send": False, "status": "pending_gmail_draft"}


def owners_with_work(items: list[dict], as_of: date) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in select(items, as_of):
        if r["status"] in ("open", "overdue") and r["owner_state"] == "resolved":
            out.setdefault(r["owner"], []).append(r)
    return out


def write_drafts(drafts: list[dict], outdir: Path) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    paths = []
    for d in drafts:
        base = outdir / slug(d["owner"])
        base.with_suffix(".json").write_text(json.dumps(d, indent=2), encoding="utf-8")
        base.with_suffix(".txt").write_text(
            f"To: {d['to'] or '(no email on file)'}\nSubject: {d['subject']}\n\n{d['body']}\n",
            encoding="utf-8")
        paths.append(base.with_suffix(".json"))
    manifest = {"send": False, "note": "Create Gmail DRAFTS only. Never send.",
                "drafts": [{"owner": d["owner"], "to": d["to"], "subject": d["subject"],
                            "file": f"{slug(d['owner'])}.json",
                            "status": "pending_gmail_draft"} for d in drafts]}
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return paths
