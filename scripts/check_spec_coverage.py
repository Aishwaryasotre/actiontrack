#!/usr/bin/env python3
"""Fail if a requirement ID in the spec is not carried by the NAME of at least one test.

Only `def test_...` names count (docstrings and comments do not), e.g. test_overdue_LST_03.
Usage: check_spec_coverage.py [tests_dir]
"""
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
tests_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "tests"
spec = (root / "specs/001-actiontrack/spec.md").read_text()
ids = sorted(set(re.findall(r"^\| ((?:ING|LST|DON|ASN|FUP|GML|NFR)-\d\d) \|", spec, re.M)))
names = re.findall(r"def (test_\w+)", "".join(p.read_text() for p in tests_dir.glob("test_*.py")))
covered = {i: [n for n in names if re.search(rf"(?<![0-9A-Z]){i.replace('-', '_')}(?![0-9])", n)] for i in ids}
manual = {"GML-02": "live Gmail check; see specs/001-actiontrack/qa/gmail-verification.md"}
missing = [i for i in ids if not covered[i] and i not in manual]
print(f"{len(ids)} requirements: {sum(bool(v) for v in covered.values())} covered by a named test, "
      f"{len(manual)} manual, {len(missing)} missing")
for i in missing:
    print(f"  MISSING TEST: {i}")
sys.exit(1 if missing else 0)
