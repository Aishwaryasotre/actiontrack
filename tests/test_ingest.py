"""Spec ING-01, 02, 04, 05, 10, 11, 12."""
import unittest

from actiontrack.ingest import ingest_folder
from tests.helpers import fresh_db, make_notes, note, run


def items_of(res):
    return {(i["owner"] or i["owner_raw"] or i["owner_state"], i["task"]): i for i in res.items}


class Ingest(unittest.TestCase):
    def test_non_md_ignored_and_missing_folder_ING_01(self):
        d = make_notes({"a.md": note(body="- [ ] Sam to a"), "b.txt": "- [ ] Sam to b"})
        res = ingest_folder(d)
        self.assertEqual((len(res.parsed), len(res.ignored)), (1, 1))
        code, _, err = run("--db", fresh_db(), "ingest", str(d / "nope"))
        self.assertEqual(code, 2)
        self.assertIn("not found", err)

    def test_recursive_ING_01(self):
        d = make_notes({"sub/2026-09-01-a.md": note(body="- [ ] Sam to a")})
        self.assertEqual(len(ingest_folder(d).items), 1)

    def test_front_matter_ING_02(self):
        d = make_notes({"n.md": "---\ntitle: Stand\ndate: 2026-09-16\nattendees: [Sam Okafor, Priya Nair]\n---\n"
                                "- [ ] Priya to send it by Friday\n"})
        res = ingest_folder(d)
        it = res.items[0]
        self.assertEqual(it["owner"], "Priya Nair")
        self.assertEqual(it["due"], "2026-09-18")
        self.assertEqual(it["occurrences"][0]["meeting_title"], "Stand")

    def test_title_ignores_sub_headings_ING_02(self):
        d = make_notes({"2026-10-05-weekly-sync.md": "Date: 2026-10-05\r\nAttendees: Sam Okafor\r\n\r\n"
                                                    "## Action items\r\n- [ ] Sam to ship it\r\n"})
        self.assertEqual(ingest_folder(d).items[0]["occurrences"][0]["meeting_title"], "2026-10-05-weekly-sync")
        d = make_notes({"n.md": "# Real title\nDate: 2026-10-05\n## Action items\n- [ ] Sam to a\n"})
        self.assertEqual(ingest_folder(d).items[0]["occurrences"][0]["meeting_title"], "Real title")

    def test_crlf_and_bom_ING_02(self):
        d = make_notes({"n.md": b"\xef\xbb\xbf# T\r\nDate: 2026-10-05\r\nAttendees: Sam Okafor, Priya Nair\r\n- [ ] Sam to ship by Friday\r\n"})
        it = ingest_folder(d).items[0]
        self.assertEqual((it["owner"], it["due"]), ("Sam Okafor", "2026-10-09"))

    def test_assign_survives_reingest_ING_12(self):
        d = make_notes({"n.md": note(attendees="Priya Nair, Priya Shah", body="- [ ] Priya to a")})
        db = fresh_db()
        run("--db", db, "ingest", str(d))
        run("--db", db, "assign", "1", "Priya Shah")
        run("--db", db, "ingest", str(d))
        import json
        r = json.loads(run("--db", db, "list", "--json")[1])[0]
        self.assertEqual((r["owner"], r["owner_state"]), ("Priya Shah", "resolved"))

    def test_bullet_styles_and_nesting_ING_04(self):
        body = ("- [ ] Sam to a\n* [ ] Sam to b\n+ [ ] Sam to c\n  - [ ] Sam to d\n- [x] Sam to e\n"
                "- [X] Sam to f\nACTION: Sam to g\n"
                "| Owner | Action | Due |\n|---|---|---|\n| Sam | h | 2026-09-09 |\n")
        res = ingest_folder(make_notes({"n.md": note(body=body)}))
        by = {i["task"]: i for i in res.items}
        self.assertEqual(sorted(by), list("abcdefgh"))
        self.assertTrue(by["e"]["done"] and by["f"]["done"] and not by["a"]["done"])
        self.assertEqual(by["h"]["due"], "2026-09-09")

    def test_items_outside_action_heading_ING_04(self):
        res = ingest_folder(make_notes({"n.md": note(body="## Other\n- [ ] Sam to a")}))
        self.assertEqual(len(res.items), 1)

    def test_not_extracted_ING_05(self):
        body = ("> - [ ] Sam to quoted\n```\n- [ ] Sam to fenced\n```\n"
                "<!-- - [ ] Sam to commented -->\n<!--\n- [ ] Sam to multi\n-->\n- [ ] Sam to real\n")
        res = ingest_folder(make_notes({"n.md": note(body=body)}))
        self.assertEqual([i["task"] for i in res.items], ["real"])

    def test_malformed_skipped_not_fatal_ING_11(self):
        d = make_notes({
            "empty.md": "", "bin.md": b"\x00\x01\xff\xfe" * 10, "bad-utf8.md": b"\xff\xfe\xfa- [ ] x",
            "nodate.md": "- [ ] Sam to x", "ok.md": note(body="- [ ] Sam to x")})
        res = ingest_folder(d)
        self.assertEqual(res.parsed, ["ok.md"])
        self.assertEqual({f for f, _ in res.skipped}, {"empty.md", "bin.md", "bad-utf8.md", "nodate.md"})
        code, out, _ = run("--db", fresh_db(), "ingest", str(d))
        self.assertEqual(code, 0)
        self.assertIn("skipped      : 4", out)

    def test_filename_date_fallback_warns_ING_03(self):
        d = make_notes({"2026-10-03-x.md": "# M\nDate: sometime last week\n- [ ] Sam to go by Friday\n"})
        res = ingest_folder(d)
        self.assertEqual(res.items[0]["due"], "2026-10-09")
        self.assertTrue(any("filename date" in w for w in res.warnings))

    def test_no_owner_no_due_ING_08(self):
        res = ingest_folder(make_notes({"n.md": note(body="- [ ] book the venue\n- [ ] TBD to do y\n- [ ] Everyone to z")}))
        self.assertEqual({i["owner_state"] for i in res.items}, {"none", "group"})
        self.assertTrue(all(i["due"] is None for i in res.items))

    def test_unresolvable_due_keeps_item_ING_09(self):
        res = ingest_folder(make_notes({"n.md": note(body="- [ ] Sam to a by sometime soon")}))
        self.assertEqual(res.items[0]["due"], None)

    def test_duplicates_merge_ING_10(self):
        d = make_notes({
            "2026-09-01-a.md": note("2026-09-01", body="- [ ] Priya to send the revised quote to Acme by Friday"),
            "2026-09-08-b.md": note("2026-09-08", body="- [ ] Priya N. to send revised quote to Acme — by Friday"),
            "2026-09-15-c.md": note("2026-09-15", body="- [x] Priya to send the revised quote to Acme")})
        res = ingest_folder(d)
        self.assertEqual(len(res.items), 1)
        it = res.items[0]
        self.assertEqual(len(it["occurrences"]), 3)
        self.assertTrue(it["done"])
        self.assertEqual(it["due"], "2026-09-11")   # latest occurrence that has a due date

    def test_reopen_warns_ING_10(self):
        d = make_notes({"2026-09-01-a.md": note("2026-09-01", body="- [x] Sam to fix it"),
                        "2026-09-08-b.md": note("2026-09-08", body="- [ ] Sam to fix it")})
        res = ingest_folder(d)
        self.assertFalse(res.items[0]["done"])
        self.assertTrue(any("reopened" in w for w in res.warnings))

    def test_same_task_different_owner_not_merged_ING_10(self):
        res = ingest_folder(make_notes({"n.md": note(body="- [ ] Sam to a\n- [ ] Priya to a")}))
        self.assertEqual(len(res.items), 2)

    def test_multi_owner_splits_ING_06(self):
        res = ingest_folder(make_notes({"n.md": note(body="- [ ] Priya & Sam to agree on x")}))
        self.assertEqual(sorted(i["owner"] for i in res.items), ["Priya Nair", "Sam Okafor"])

    def test_idempotent_and_manual_state_survives_ING_12(self):
        d = make_notes({"n.md": note(body="- [ ] Sam to a\n- [ ] Sam to b")})
        db = fresh_db()
        run("--db", db, "ingest", str(d))
        run("--db", db, "done", "1")
        run("--db", db, "ingest", str(d))
        code, out, _ = run("--db", db, "--as-of", "2026-09-02", "list", "--json")
        import json
        rows = json.loads(out)
        self.assertEqual([(r["id"], r["status"]) for r in rows], [(2, "open"), (1, "done")])

    def test_removed_item_dropped_unless_manual_ING_12(self):
        d = make_notes({"n.md": note(body="- [ ] Sam to a\n- [ ] Sam to b")})
        db = fresh_db()
        run("--db", db, "ingest", str(d))
        run("--db", db, "done", "2")
        (d / "n.md").write_text(note(body=""))
        run("--db", db, "ingest", str(d))
        import json
        rows = json.loads(run("--db", db, "list", "--json")[1])
        self.assertEqual([r["id"] for r in rows], [2])


if __name__ == "__main__":
    unittest.main()
