"""Date parsing and relative-date resolution (spec ING-03, ING-09)."""
from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
MONTHS["sept"] = 9
WEEKDAYS = {d.lower(): i for i, d in enumerate(calendar.day_name)}
WEEKDAYS.update({d.lower(): i for i, d in enumerate(calendar.day_abbr)})
WEEKDAYS.update({"tues": 1, "thur": 3, "thurs": 3})

_MON = r"(?:" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")"
_WDY = r"(?:" + "|".join(sorted(WEEKDAYS, key=len, reverse=True)) + r")"

ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DAY_MON = re.compile(rf"(?:{_WDY}\.?,?\s+)?(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MON})\b\.?(?:,?\s+(\d{{4}}))?", re.I)
_MON_DAY = re.compile(rf"(?:{_WDY}\.?,?\s+)?({_MON})\b\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}}))?", re.I)


def parse_header_date(text: str) -> date | None:
    """Parse a meeting header date: ISO, '9 September 2026', 'Monday, 14 September 2026'."""
    text = (text or "").strip()
    m = ISO_RE.search(text)
    if m:
        return _safe(int(m[1]), int(m[2]), int(m[3]))
    m = _DAY_MON.search(text)
    if m and m[3]:
        return _safe(int(m[3]), MONTHS[m[2].lower()], int(m[1]))
    m = _MON_DAY.search(text)
    if m and m[3]:
        return _safe(int(m[3]), MONTHS[m[1].lower()], int(m[2]))
    return None


def _safe(y: int, mo: int, d: int) -> date | None:
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _with_year(meeting: date, mo: int, d: int, year: int | None) -> date | None:
    if year:
        return _safe(year, mo, d)
    cand = _safe(meeting.year, mo, d)
    if cand and (meeting - cand).days > 60:
        cand = _safe(meeting.year + 1, mo, d)
    return cand


def _next_weekday(meeting: date, wd: int) -> date:
    """First `wd` strictly after the meeting date."""
    delta = (wd - meeting.weekday()) % 7
    return meeting + timedelta(days=delta or 7)


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _end_of_month(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


# Ordered: most specific first. Each returns (date | None) from the match.
def _patterns(meeting: date):
    return [
        (ISO_RE, lambda m: _safe(int(m[1]), int(m[2]), int(m[3]))),
        (_DAY_MON, lambda m: _with_year(meeting, MONTHS[m[2].lower()], int(m[1]), int(m[3]) if m[3] else None)),
        (_MON_DAY, lambda m: _with_year(meeting, MONTHS[m[1].lower()], int(m[2]), int(m[3]) if m[3] else None)),
        (re.compile(r"(?:end\s+of\s+(?:the\s+)?day|eod|cob)\s+tomorrow\b", re.I), lambda m: meeting + timedelta(days=1)),
        (re.compile(r"tomorrow\b", re.I), lambda m: meeting + timedelta(days=1)),
        (re.compile(r"(?:today|tonight|eod|cob|end\s+of\s+(?:the\s+)?day)\b", re.I), lambda m: meeting),
        (re.compile(r"(?:end\s+of|eo)\s+(?:the\s+)?month\b", re.I), lambda m: _end_of_month(meeting)),
        (re.compile(r"(?:end\s+of|eo)\s+next\s+week\b", re.I), lambda m: _monday(meeting) + timedelta(days=11)),
        (re.compile(r"(?:end\s+of|eo)\s+(?:the\s+|this\s+)?week\b", re.I), lambda m: _monday(meeting) + timedelta(days=4)),
        (re.compile(r"next\s+week\b", re.I), lambda m: _monday(meeting) + timedelta(days=11)),
        (re.compile(rf"mid[-\s]({_MON})\b", re.I), lambda m: _with_year(meeting, MONTHS[m[1].lower()], 15, None)),
        (re.compile(rf"next\s+({_WDY})\b", re.I), lambda m: _monday(meeting) + timedelta(days=7 + WEEKDAYS[m[1].lower()])),
        (re.compile(rf"(?:this\s+)?({_WDY})\b\.?", re.I), lambda m: _next_weekday(meeting, WEEKDAYS[m[1].lower()])),
    ]


def parse_due_at_start(text: str, meeting: date) -> tuple[date | None, int]:
    """Try to read a due phrase at the very start of `text`.

    Returns (date, characters consumed) or (None, 0)."""
    text = text.lstrip()
    for rx, fn in _patterns(meeting):
        m = rx.match(text)
        if m:
            d = fn(m)
            if d:
                return d, m.end()
    return None, 0


MARKER_RE = re.compile(r"\b(by|due|before|until|on)\b[:\s]+", re.I)


def extract_due(text: str, meeting: date) -> tuple[str, date | None, str | None, bool]:
    """Find the last marker + parseable date phrase in `text`.

    Returns (task_text_without_due_phrase, due_date, raw_phrase, unresolved_phrase_seen).
    """
    best = None
    unresolved = False
    for m in MARKER_RE.finditer(text):
        rest = text[m.end():]
        d, used = parse_due_at_start(rest, meeting)
        if d:
            best = (m.start(), m.end() + used, d, rest[:used].strip())
        elif re.match(r"(next|this|end|eo|mid|the end)\b", rest, re.I):
            unresolved = True
    if not best:
        m = re.search(r"[\s,;\u2013\u2014-]+\b(tomorrow|tonight|today|eod)\s*[.!]?$", text, re.I)
        if m:  # bare trailing relative word, e.g. "circulate the summary tomorrow"
            d, _ = parse_due_at_start(m[1], meeting)
            return text[:m.start()].strip(), d, m[1], False
        return text.strip(), None, None, unresolved
    start, end, d, raw = best
    cleaned = (text[:start] + " " + text[end:]).strip()
    cleaned = re.sub(r"[\s,;:–—-]+$", "", cleaned)
    return cleaned, d, raw, False
