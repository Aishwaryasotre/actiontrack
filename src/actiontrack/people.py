"""Owner parsing and same-first-name resolution (spec ING-06, ING-07, ING-08)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

GROUP_WORDS = {"everyone", "everybody", "team", "all", "we", "us"}
NONE_WORDS = {"someone", "somebody", "tbd", "nobody", "tba", "unassigned", "?"}

_NAME_TOKEN = r"@?[A-Z][\w'’-]*\.?"
_OWNER_PART = rf"{_NAME_TOKEN}(?:\s+{_NAME_TOKEN})?"
OWNER_TO_RE = re.compile(
    rf"^(?P<owners>{_OWNER_PART}(?:\s*(?:&|,|\band\b)\s*{_OWNER_PART})*)"
    rf"(?:\s*(?P<remark>\((?:with|and|\+)[^)]*\)))?\s+(?:to|will|should|needs to|must)\s+(?P<task>.+)$"
)
OWNER_AT_RE = re.compile(r"^@(?P<owners>[\w.'-]+)\s*:?\s+(?P<task>.+)$")
OWNER_COLON_RE = re.compile(rf"^(?P<owners>{_OWNER_PART})\s*:\s+(?P<task>.+)$")


@dataclass
class Owner:
    state: str               # resolved | ambiguous | group | none
    name: str | None = None  # full name when resolved, else raw text
    raw: str = ""
    candidates: list[str] = field(default_factory=list)


def split_owner(text: str) -> tuple[list[str], str]:
    """Return ([raw owner strings], task). Empty owners list when no owner found."""
    text = text.strip()
    for rx in (OWNER_AT_RE, OWNER_TO_RE, OWNER_COLON_RE):
        m = rx.match(text)
        if m:
            parts = re.split(r"\s*(?:&|,|\band\b)\s*", m["owners"])
            task = m["task"].strip()
            remark = m.groupdict().get("remark")
            if remark:
                task = f"{task} {remark}"
            return [p.strip().lstrip("@") for p in parts if p.strip()], task
    return [], text


class Roster:
    """All full names seen in Attendees fields, used to resolve first names."""

    def __init__(self) -> None:
        self.names: set[str] = set()

    def add(self, names: list[str]) -> None:
        for n in names:
            n = re.sub(r"\s+", " ", n).strip()
            if n:
                self.names.add(n)

    def _match(self, token: str, pool) -> list[str]:
        parts = token.replace(".", ". ").split()
        first = parts[0].lower()
        second = parts[1].strip(".").lower() if len(parts) > 1 else ""
        out = []
        for full in sorted(pool):
            fp = full.split()
            if fp[0].lower() != first:
                continue
            if second and not (len(fp) > 1 and fp[-1].lower().startswith(second)):
                continue
            out.append(full)
        return out

    def resolve(self, raw: str, attendees: list[str]) -> Owner:
        key = raw.strip().strip(".").lower()
        if key in GROUP_WORDS:
            return Owner("group", "(group)", raw)
        if key in NONE_WORDS:
            return Owner("none", None, raw)
        for pool in (attendees, self.names):
            hits = self._match(raw, pool)
            if len(hits) == 1:
                return Owner("resolved", hits[0], raw)
            if len(hits) > 1:
                return Owner("ambiguous", None, raw, hits)
        return Owner("resolved", _title(raw), raw)  # unknown person, keep as written

    def find_person(self, query: str) -> list[str]:
        """Match a CLI --owner / followup argument to full names."""
        q = query.strip().lower()
        exact = [n for n in self.names if n.lower() == q]
        if exact:
            return exact
        return sorted(n for n in self.names if q and q in n.lower().split())  # whole words only


def _title(raw: str) -> str:
    return " ".join(w[:1].upper() + w[1:] for w in raw.split())
