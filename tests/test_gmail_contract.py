"""Spec GML-01 (skill contract, mock connector, static SKILL.md check), FUP-02, FUP-04.

IMPORTANT: the real Gmail step is performed by Claude following SKILL.md. It cannot be unit tested.
`MockGmail` + `skill_procedure` below are a TEST DOUBLE of SKILL.md step 4. They prove that the manifest
the CLI writes is sufficient to create drafts with draft-only operations, and that any other Gmail
operation would be caught. No live Gmail call is made anywhere in this file.
"""
import json
import re
import unittest
from pathlib import Path

from tests.helpers import fresh_db, make_notes, note, run

SKILL = Path(__file__).resolve().parent.parent / ".claude/skills/actiontrack/SKILL.md"
ALLOWED_GMAIL_OPS = {"create_draft", "list_drafts"}
AS_OF = "2026-09-20"


class ForbiddenGmailOperation(AssertionError):
    pass


class MockGmail:
    """Records calls. Any operation other than create_draft / list_drafts raises."""

    def __init__(self, existing=None):
        self.calls = []
        self.existing = existing or []

    def create_draft(self, to, subject, body):
        assert isinstance(to, list), "Gmail create_draft needs `to` as a list"
        self.calls.append(("create_draft", {"to": to, "subject": subject, "body": body}))
        return {"id": f"d{len(self.calls)}", "labelIds": ["DRAFT"]}

    def list_drafts(self, query):
        self.calls.append(("list_drafts", {"query": query}))
        return list(self.existing)

    def __getattr__(self, name):          # send_message, reply, forward, update_draft, delete_draft, ...
        raise ForbiddenGmailOperation(f"forbidden Gmail operation attempted: {name}")


def skill_procedure(drafts_dir: Path, gmail: MockGmail):
    """Test double of SKILL.md step 4: duplicate check, then one create_draft per manifest entry."""
    manifest = json.loads((drafts_dir / "manifest.json").read_text())
    assert manifest["send"] is False
    created = []
    for entry in manifest["drafts"]:
        d = json.loads((drafts_dir / entry["file"]).read_text())
        existing = gmail.list_drafts(query="subject:Follow-up")
        if any(e["subject"] == d["subject"] and e["to"] == ([d["to"]] if d["to"] else []) for e in existing):
            continue
        created.append(gmail.create_draft(to=[d["to"]] if d["to"] else [], subject=d["subject"], body=d["body"]))
    return created


BODY = ("- [ ] Sam to overdue old by 2026-09-05\n- [ ] Sam to future by 2026-09-30\n- [x] Sam to finished by 2026-09-03\n"
        "- [ ] Priya Nair to priya task by 2026-09-10\n- [ ] Everyone to team thing\n")


def followup_all(body=BODY, people=None, attendees="Sam Okafor, Priya Nair, Priya Shah"):
    d = make_notes({"2026-09-01-a.md": note("2026-09-01", attendees, body)})
    db = fresh_db()
    run("--db", db, "ingest", str(d))
    args = ["--db", db, "--as-of", AS_OF, "followup", "--all", "--out", str(d / "drafts")]
    if people is not None:
        (d / "p.json").write_text(people if isinstance(people, str) else json.dumps(people))
        args += ["--people", str(d / "p.json")]
    else:
        args += ["--people", str(d / "absent.json")]
    code, out, err = run(*args)
    return d, code, out, err


class MockConnectorContract(unittest.TestCase):
    def test_one_create_draft_per_entry_and_nothing_else_GML_01(self):
        d, code, _, _ = followup_all(people={"Sam Okafor": "sam@example.com", "Priya Nair": "priya@example.com"})
        gmail = MockGmail()
        created = skill_procedure(d / "drafts", gmail)
        self.assertEqual(len(created), 2)
        ops = [c[0] for c in gmail.calls]
        self.assertEqual(ops.count("create_draft"), 2)
        self.assertTrue(set(ops) <= ALLOWED_GMAIL_OPS, ops)
        self.assertTrue(all(c["labelIds"] == ["DRAFT"] for c in created))

    def test_empty_recipient_is_empty_list_never_guessed_GML_01(self):
        d, _, out, _ = followup_all(people={"Sam": "sam@example.com", "priya": "p@example.com"})   # first names only
        gmail = MockGmail()
        skill_procedure(d / "drafts", gmail)
        for _, kw in (c for c in gmail.calls if c[0] == "create_draft"):
            self.assertEqual(kw["to"], [])
        self.assertIn("no email", out)

    def test_existing_identical_draft_not_duplicated_GML_01(self):
        d, *_ = followup_all()
        first = MockGmail()
        skill_procedure(d / "drafts", first)
        existing = [{"subject": kw["subject"], "to": kw["to"]} for n, kw in first.calls if n == "create_draft"]
        second = MockGmail(existing=existing)
        self.assertEqual(skill_procedure(d / "drafts", second), [])
        self.assertNotIn("create_draft", [c[0] for c in second.calls])

    def test_mock_catches_every_forbidden_operation_GML_01(self):
        g = MockGmail()
        for op in ("send_message", "reply", "forward", "update_draft", "delete_draft", "trash_message"):
            with self.assertRaises(ForbiddenGmailOperation, msg=op):
                getattr(g, op)

    def test_manifest_never_requests_a_send_GML_01(self):
        d, *_ = followup_all()
        manifest = json.loads((d / "drafts" / "manifest.json").read_text())
        self.assertIs(manifest["send"], False)
        for e in manifest["drafts"]:
            self.assertEqual(e["status"], "pending_gmail_draft")
            self.assertIs(json.loads((d / "drafts" / e["file"]).read_text())["send"], False)


class SkillFileStaticCheck(unittest.TestCase):
    def setUp(self):
        self.text = SKILL.read_text()
        lines = self.text.splitlines()
        start = next(i for i, l in enumerate(lines) if "Forbidden Gmail tools" in l)
        end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("   - If the Gmail tools"))
        self.forbidden_block = "\n".join(lines[start:end])
        self.rest = "\n".join(lines[:start] + lines[end:])

    def test_only_draft_tools_are_instructed_GML_01(self):
        used = set(re.findall(r"mcp__Gmail__([a-z_]+)", self.rest))
        self.assertEqual(used, ALLOWED_GMAIL_OPS)
        for bad in ("send_message", "reply", "forward", "update_draft", "delete_draft"):
            self.assertNotIn(bad, self.rest, f"{bad} mentioned outside the forbidden list")

    def test_forbidden_list_names_the_send_paths_GML_01(self):
        for op in ("send_message", "reply", "forward"):
            self.assertIn(op, self.forbidden_block)

    def test_confirmation_precedes_creation_and_duplicate_check_precedes_create_GML_01(self):
        t = self.text
        self.assertLess(t.index("Ask for confirmation"), t.index("mcp__Gmail__create_draft"))
        self.assertLess(t.index("Duplicate check first"), t.index("Call **`mcp__Gmail__create_draft`**"))

    def test_skill_handles_missing_connector_without_fallback_GML_01(self):
        self.assertIn("Do not fall back to any other mail method", self.text)


class DraftContent(unittest.TestCase):
    def test_owner_isolation_done_excluded_and_overdue_arithmetic_FUP_02(self):
        d, code, _, _ = followup_all()
        sam = json.loads((d / "drafts/sam-okafor.json").read_text())
        priya = json.loads((d / "drafts/priya-nair.json").read_text())
        self.assertEqual(code, 0)
        self.assertIn("overdue old - was due 2026-09-05 (15 days late)", sam["body"])
        self.assertIn("future - due 2026-09-30", sam["body"])
        self.assertNotIn("finished", sam["body"])                         # completed item excluded
        self.assertNotIn("priya task", sam["body"])                       # other owner's item excluded
        self.assertNotIn("team thing", sam["body"] + priya["body"])       # group item excluded
        self.assertIn("priya task", priya["body"])
        self.assertNotIn("overdue old", priya["body"])
        self.assertTrue(sam["body"].index("overdue old") < sam["body"].index("future"))   # overdue before open
        self.assertFalse((d / "drafts/priya-shah.json").exists())          # nothing open -> no draft

    def test_source_meeting_and_date_cited_FUP_02(self):
        d, *_ = followup_all()
        self.assertIn("[T, 2026-09-01]", json.loads((d / "drafts/sam-okafor.json").read_text())["body"])


class PeopleFile(unittest.TestCase):
    def _sam(self, people):
        d, code, out, err = followup_all(people=people)
        f = d / "drafts/sam-okafor.json"
        return code, out, err, (json.loads(f.read_text())["to"] if f.exists() else None)

    def test_valid_and_case_insensitive_full_name_FUP_04(self):
        self.assertEqual(self._sam({"sam OKAFOR": "sam@example.com"})[3], "sam@example.com")

    def test_first_name_key_never_matches_FUP_04(self):
        self.assertEqual(self._sam({"Sam": "sam@example.com"})[3], "")

    def test_unusable_addresses_are_dropped_with_warning_FUP_04(self):
        for bad in (None, "", "not-an-email", "a@x.com, b@x.com", "a@x.com;b@x.com",
                    "sam@example.com\nBcc: evil@example.com", "Sam <sam@example.com>", 42):
            code, out, err, to = self._sam({"Sam Okafor": bad})
            self.assertEqual((code, to), (0, ""), repr(bad))
            self.assertNotIn("Traceback", err)
        code, out, _, _ = self._sam({"Sam Okafor": "not-an-email"})
        self.assertIn("invalid email", out)

    def test_malformed_or_wrong_shape_people_file_exits_2_FUP_04(self):
        for text in ('{"Sam Okafor": "sam@example.com",', '["sam@example.com"]', '"text"', ""):
            code, out, err, to = self._sam(text)
            self.assertEqual(code, 2, repr(text))
            self.assertIsNone(to)                                        # no drafts written
            self.assertIn("people file", err)
            self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()
