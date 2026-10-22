"""Spec LST-01..05, DON-01, ASN-01, FUP-01..06, NFR-03."""
import json
import unittest
from pathlib import Path

from tests.helpers import fresh_db, make_notes, note, run

AS_OF = "2026-09-20"
BODY = (
    "- [ ] Sam to overdue old by 2026-09-05\n"       # 1 overdue 15d
    "- [ ] Sam to overdue recent by 2026-09-15\n"    # 2 overdue 5d
    "- [ ] Sam to future by 2026-09-30\n"            # 3 open
    "- [ ] Sam to nodate\n"                          # 4 open, no due
    "- [x] Sam to finished by 2026-09-03\n"          # 5 done
    "- [ ] Priya Nair to p1 by 2026-09-10\n"         # 6 overdue (Priya Nair)
    "- [ ] Everyone to team thing\n"                 # 7 group
)


def setup(body=BODY, attendees="Sam Okafor, Priya Nair, Priya Shah"):
    d = make_notes({"2026-09-01-a.md": note("2026-09-01", attendees, body)})
    db = fresh_db()
    run("--db", db, "ingest", str(d))
    return db, d


def lst(db, *args):
    return json.loads(run("--db", db, "--as-of", AS_OF, "list", "--json", *args)[1])


class List(unittest.TestCase):
    def test_statuses_and_exclusive_open_LST_03(self):
        db, _ = setup()
        by = {r["task"]: r["status"] for r in lst(db)}
        self.assertEqual(by["overdue old"], "overdue")
        self.assertEqual(by["future"], "open")
        self.assertEqual(by["nodate"], "open")
        self.assertEqual(by["finished"], "done")
        open_tasks = {r["task"] for r in lst(db, "--status", "open")}
        self.assertNotIn("overdue old", open_tasks)

    def test_due_today_is_not_overdue_LST_03(self):
        db, _ = setup("- [ ] Sam to a by 2026-09-20")
        self.assertEqual(lst(db)[0]["status"], "open")

    def test_filters_combine_LST_02(self):
        db, _ = setup()
        self.assertEqual({r["task"] for r in lst(db, "--owner", "sam", "--status", "overdue")},
                         {"overdue old", "overdue recent"})
        self.assertEqual({r["task"] for r in lst(db, "--due-before", "2026-09-12")},
                         {"overdue old", "finished", "p1"})   # strictly before; no-due never matches
        self.assertEqual([r["task"] for r in lst(db, "--owner", "Priya Nair")], ["p1"])

    def test_owner_fragments_never_match_LST_02(self):
        db, _ = setup()
        for frag in ("sa", "am", "okaf", "pri"):
            self.assertEqual(lst(db, "--owner", frag), [], frag)
        self.assertEqual(len(lst(db, "--owner", "Okafor")), 5)       # whole surname is fine

    def test_ordering_LST_05(self):
        db, _ = setup()
        self.assertEqual([r["task"] for r in lst(db)],
                         ["overdue old", "p1", "overdue recent", "future", "nodate", "team thing", "finished"])

    def test_table_output_and_empty_LST_01(self):
        db, _ = setup()
        out = run("--db", db, "--as-of", AS_OF, "list", "--owner", "sam")[1]
        for col in ("ID", "STATUS", "OWNER", "DUE", "TASK", "SOURCE"):
            self.assertIn(col, out)
        self.assertIn("overdue 15d", out)
        self.assertIn("No items.", run("--db", db, "list", "--owner", "nobody")[1])

    def test_unassigned_labels_ING_08(self):
        db, _ = setup()
        self.assertIn("(group)", run("--db", db, "--as-of", AS_OF, "list")[1])

    def test_json_has_fields_LST_04(self):
        db, _ = setup()
        r = lst(db)[0]
        for k in ("id", "owner", "task", "due", "status", "sources"):
            self.assertIn(k, r)


class DoneAssign(unittest.TestCase):
    def test_done_DON_01(self):
        db, _ = setup()
        self.assertEqual(run("--db", db, "done", "4")[0], 0)
        self.assertEqual({r["id"]: r["status"] for r in lst(db)}[4], "done")
        code, out, _ = run("--db", db, "done", "4")           # idempotent
        self.assertEqual(code, 0)
        self.assertIn("already done", out)

    def test_done_unknown_id_DON_01(self):
        db, _ = setup()
        code, out, err = run("--db", db, "done", "999", "4")
        self.assertEqual(code, 1)
        self.assertIn("no item with id 999", err)
        self.assertIn("#4 marked done", out)                   # others still processed

    def test_assign_ambiguous_ASN_01(self):
        db, _ = setup("- [ ] Priya to thing", attendees="Priya Nair, Priya Shah")
        self.assertEqual(lst(db)[0]["owner_state"], "ambiguous")
        self.assertEqual(run("--db", db, "assign", "1", "priya shah")[0], 0)
        r = lst(db)[0]
        self.assertEqual((r["owner"], r["owner_state"]), ("Priya Shah", "resolved"))
        self.assertEqual(run("--db", db, "assign", "1", "Nobody Here")[0], 1)


class Followup(unittest.TestCase):
    def test_draft_content_and_files_FUP_02_FUP_03(self):
        db, d = setup()
        out_dir = d / "drafts"
        people = d / "people.json"
        people.write_text(json.dumps({"Sam Okafor": "sam@example.com"}))
        code, out, _ = run("--db", db, "--as-of", AS_OF, "followup", "Sam Okafor",
                           "--people", str(people), "--out", str(out_dir))
        self.assertEqual(code, 0)
        draft = json.loads((out_dir / "sam-okafor.json").read_text())
        self.assertEqual(draft["to"], "sam@example.com")
        self.assertFalse(draft["send"])
        body = draft["body"]
        self.assertIn("Overdue (2)", body)
        self.assertIn("15 days late", body)
        self.assertIn("Open (2)", body)
        self.assertIn("no due date", body)
        self.assertNotIn("finished", body)                     # done excluded
        self.assertNotIn("team thing", body)
        self.assertLess(body.index("overdue old"), body.index("future"))
        self.assertEqual(draft["item_ids"], [1, 2, 3, 4])
        manifest = json.loads((out_dir / "manifest.json").read_text())
        self.assertFalse(manifest["send"])
        self.assertEqual(manifest["drafts"][0]["status"], "pending_gmail_draft")
        self.assertTrue((out_dir / "sam-okafor.txt").exists())
        self.assertIn("Nothing was sent", out)

    def test_never_sends_FUP_03(self):
        import actiontrack, re
        src = "".join(p.read_text() for p in Path(actiontrack.__file__).parent.glob("*.py"))
        self.assertIsNone(re.search(r"smtplib|\.send\(|sendmail|messages/send|urlopen|requests\.", src))

    def test_ambiguous_argument_FUP_01(self):
        db, d = setup()
        code, _, err = run("--db", db, "followup", "Priya", "--out", str(d / "o"))
        self.assertEqual(code, 2)
        self.assertIn("Priya Nair", err)
        self.assertIn("Priya Shah", err)
        self.assertFalse((d / "o").exists())
        self.assertEqual(run("--db", db, "followup", "Zed", "--out", str(d / "o"))[0], 1)

    def test_unique_first_name_ok_FUP_01(self):
        db, d = setup()
        code, _, _ = run("--db", db, "--as-of", AS_OF, "followup", "sam", "--out", str(d / "o"))
        self.assertEqual(code, 0)
        self.assertTrue((d / "o" / "sam-okafor.json").exists())

    def test_fragment_cannot_select_a_person_FUP_01(self):
        db, d = setup()
        code, _, err = run("--db", db, "--as-of", AS_OF, "followup", "okaf", "--out", str(d / "o"))
        self.assertEqual(code, 1)
        self.assertFalse((d / "o").exists())                    # no draft for a typo

    def test_missing_email_warns_FUP_04(self):
        db, d = setup()
        code, out, _ = run("--db", db, "--as-of", AS_OF, "followup", "Sam Okafor",
                           "--people", str(d / "none.json"), "--out", str(d / "o"))
        self.assertIn("no email", out)
        self.assertEqual(json.loads((d / "o" / "sam-okafor.json").read_text())["to"], "")

    def test_nothing_open_no_draft_FUP_05(self):
        db, d = setup()
        run("--db", db, "done", "1", "2", "3", "4")
        code, out, _ = run("--db", db, "--as-of", AS_OF, "followup", "Sam Okafor", "--out", str(d / "o"))
        self.assertEqual(code, 0)
        self.assertIn("nothing open", out)
        self.assertFalse((d / "o").exists())

    def test_all_and_left_out_report_FUP_01_FUP_06(self):
        db, d = setup(BODY + "- [ ] Priya to amb\n")
        code, out, _ = run("--db", db, "--as-of", AS_OF, "followup", "--all", "--out", str(d / "o"))
        self.assertEqual(code, 0)
        self.assertTrue((d / "o" / "sam-okafor.json").exists())
        self.assertTrue((d / "o" / "priya-nair.json").exists())
        self.assertFalse((d / "o" / "priya-shah.json").exists())   # nothing open for her
        self.assertIn("Left out of follow-ups: 2", out)            # group item + ambiguous Priya
        self.assertEqual(run("--db", db, "followup")[0], 2)         # neither owner nor --all

    def test_ambiguous_items_never_in_a_draft_ING_07(self):
        db, d = setup("- [ ] Priya to amb", attendees="Priya Nair, Priya Shah")
        run("--db", db, "--as-of", AS_OF, "followup", "--all", "--out", str(d / "o"))
        self.assertFalse((d / "o").exists())


class Determinism(unittest.TestCase):
    def test_same_input_same_output_NFR_03(self):
        a, _ = setup()
        b, _ = setup()
        self.assertEqual(run("--db", a, "--as-of", AS_OF, "list")[1], run("--db", b, "--as-of", AS_OF, "list")[1])


if __name__ == "__main__":
    unittest.main()
