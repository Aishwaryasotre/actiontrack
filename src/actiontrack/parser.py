"""Parse one meeting note into metadata + raw action lines (spec ING-02..ING-09)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .dates import extract_due, parse_header_date, ISO_RE

CHECKBOX_RE = re.compile(r"^\s*[-*+]\s+\[(?P<mark>[ xX])\]\s+(?P<text>.+?)\s*$")
ACTION_RE = re.compile(r"^\s*(?:[-*+]\s+)?ACTION\s*:\s*(?P<text>.+?)\s*$")
FILENAME_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


class SkipNote(Exception):
    """Raised for a note that must be skipped; message is the reason."""


@dataclass
class RawItem:
    line: int
    checked: bool
    text: str            # text after the checkbox, owner still attached
    kind: str            # checkbox | action | table
    table_owner: str | None = None
    table_due: str | None = None


@dataclass
class Note:
    path: str
    title: str
    date: date
    attendees: list[str]
    items: list[RawItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def read_text(path: Path) -> str:
    data = path.read_bytes()
    if not data.strip():
        raise SkipNote("empty file")
    if b"\x00" in data:
        raise SkipNote("binary content (not text)")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise SkipNote("not valid UTF-8 text")


def _split_front_matter(text: str) -> tuple[dict[str, str], str, int]:
    """Return (front-matter dict, body, number of lines consumed)."""
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                fm = {}
                for ln in lines[1:i]:
                    if ":" in ln:
                        k, v = ln.split(":", 1)
                        fm[k.strip().lower()] = v.strip()
                return fm, "\n".join(lines[i + 1:]), i + 1
    return {}, text, 0


def _names(value: str) -> list[str]:
    value = value.strip().strip("[]")
    return [re.sub(r"\s+", " ", n.strip().strip("'\"")) for n in value.split(",") if n.strip()]


def parse_note(path: Path) -> Note:
    text = read_text(path)
    fm, body, offset = _split_front_matter(text)
    title = fm.get("title") or ""
    date_raw = fm.get("date", "")
    attendees = _names(fm["attendees"]) if "attendees" in fm else []

    lines = body.splitlines()
    for ln in lines:
        s = ln.strip()
        if not title:
            m = re.match(r"#\s+(?:Meeting\s*:\s*)?(.+)$", s)
            if m:
                title = m[1].strip()
        m = re.match(r"(?i)date\s*:\s*(.+)$", s)
        if m and not date_raw:
            date_raw = m[1].strip()
        m = re.match(r"(?i)attendees\s*:\s*(.+)$", s)
        if m and not attendees:
            attendees = _names(m[1])
    if not title:
        title = path.stem

    warnings: list[str] = []
    mdate = parse_header_date(date_raw) if date_raw else None
    fname = FILENAME_DATE_RE.match(path.name)
    fdate = parse_header_date(fname[1]) if fname else None
    if mdate is None:
        if fdate:
            what = f"unreadable date {date_raw!r}" if date_raw else "no date header"
            warnings.append(f"{what}; used filename date {fdate.isoformat()}")
            mdate = fdate
        else:
            raise SkipNote(
                f"no usable date (header {date_raw!r}, filename has none)" if date_raw
                else "no date in header and none in filename")
    elif fdate and fdate != mdate:
        warnings.append(f"header date {mdate} differs from filename date {fdate}")

    note = Note(str(path), title, mdate, attendees, warnings=warnings)
    note.items = _extract_items(lines, offset)
    return note


def _extract_items(lines: list[str], offset: int) -> list[RawItem]:
    items: list[RawItem] = []
    in_fence = False
    fence = ""
    in_comment = False
    table_cols: list[str] | None = None
    for idx, raw in enumerate(lines):
        lineno = idx + 1 + offset
        line = raw
        # HTML comments (may span lines)
        if in_comment:
            if "-->" in line:
                line = line.split("-->", 1)[1]
                in_comment = False
            else:
                continue
        line = re.sub(r"<!--.*?-->", "", line)
        if "<!--" in line:
            line = line.split("<!--", 1)[0]
            in_comment = True
        s = line.strip()
        # fenced code
        fm = re.match(r"^(`{3,}|~{3,})", s)
        if fm:
            if not in_fence:
                in_fence, fence = True, fm[1][0]
            elif s.startswith(fence * 3):
                in_fence = False
            continue
        if in_fence or s.startswith(">"):
            continue
        # tables
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            low = [c.lower() for c in cells]
            if "owner" in low and any(c in low for c in ("action", "task")):
                table_cols = low
                continue
            if table_cols and not re.fullmatch(r"[\s:|-]+", s):
                row = dict(zip(table_cols, cells))
                task = row.get("action") or row.get("task") or ""
                if task and row.get("owner"):
                    items.append(RawItem(lineno, False, task, "table",
                                         row["owner"], row.get("due") or None))
            continue
        table_cols = None
        m = CHECKBOX_RE.match(line)
        if m:
            items.append(RawItem(lineno, m["mark"] in "xX", m["text"], "checkbox"))
            continue
        m = ACTION_RE.match(line)
        if m:
            items.append(RawItem(lineno, False, m["text"], "action"))
    return items


def normalise_task(task: str) -> str:
    t = task.lower().replace("’", "'")
    t = re.sub(r"\b(the|a|an)\b", " ", t)
    t = re.sub(r"[^a-z0-9%\s']", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def resolve_due_text(text: str, meeting: date):
    """Thin wrapper kept here so the ingest layer imports from one place."""
    return extract_due(text, meeting)
