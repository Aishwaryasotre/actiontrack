"""Spec section 9: acceptance on the provided sample notes (36 files)."""
import json
import unittest

from actiontrack.ingest import ingest_folder
from tests.helpers import SAMPLES, fresh_db, run


class SampleAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = ingest_folder(SAMPLES)
        cls.by_task = {}
        for i in cls.res.items:
            cls.by_task.setdefault(i["task"], []).append(i)

    def test_counts_ACC_1_2(self):
        r = self.res
        self.assertEqual(r.files_seen, 6)
        self.assertEqual(len(r.ignored), 0)
        self.assertEqual(dict(r.skipped), {})
        self.assertEqual(len(r.parsed), 6)

    def test_filename_date_fallback_ACC_3(self):
        self.assertTrue(any("2026-10-03-example-pipeline.md" in w and "filename date" in w for w in self.res.warnings))
        self.assertIn("2026-10-03-example-pipeline.md", self.res.parsed)

    def test_traps_not_extracted_ACC_4(self):
        tasks = " | ".join(self.by_task)
        self.assertNotIn("purge ExampleCo test records", tasks)
        self.assertNotIn("repair the fixture", tasks)
        self.assertNotIn("reset the fixture database", tasks)

    def test_offsite_formats_ACC_5(self):
        brand = self.by_task["Refresh demo assets"][0]
        self.assertEqual((brand["owner"], brand["due"]), ("Casey Demo", "2026-10-09"))
        self.assertEqual(self.by_task["circulate the demo summary"][0]["owner"], "Jordan Example")
        self.assertEqual(self.by_task["validate the demo budget"][0]["due"], "2026-10-05")  # nested
        self.assertEqual(self.by_task["reduce sample output by 10% proposal"][0]["due"], "2026-10-09")  # * bullet
        self.assertEqual(self.by_task["propose the test rotation"][0]["due"], "2026-10-15")  # + bullet, mid-October

    def test_same_first_name_ACC_6(self):
        amb = {i["task"]: i for i in self.res.items if i["owner_state"] == "ambiguous"}
        self.assertIn("prepare the architecture overview", amb)
        self.assertIn("confirm the mock test account", amb)
        self.assertIn("rebase the demo branch", amb)  # no attendee list in that note
        self.assertEqual(self.by_task["draft the demo outline"][0]["owner"], "Casey Demo")
        self.assertEqual(self.by_task["check the demo dashboard"][0]["owner"], "Jordan Example")
        self.assertEqual(self.by_task["verify the fixture summary"][0]["owner"], "Alex Example")

    def test_duplicates_ACC_7(self):
        it = self.by_task["send the revised proposal to ExampleCo"][0]
        self.assertEqual(it["owner"], "Alex Example")
        self.assertTrue(it["done"])
        self.assertEqual(len(it["occurrences"]), 3)
        self.assertEqual(len([t for t in self.by_task if "revised proposal" in t]), 1)

    def test_unassigned_ACC_8(self):
        states = {t: v[0]["owner_state"] for t, v in self.by_task.items()}
        self.assertEqual(states["review the prototype before the next review"], "group")
        self.assertEqual(states["write the design-system changelog"], "none")
        self.assertEqual(states["update the CRM notes"], "none")

    def test_from_is_not_due_ACC_9(self):
        self.assertIsNone(self.by_task["freeze fixture edits from 9 Oct"][0]["due"])

    def test_cli_end_to_end(self):
        db = fresh_db()
        code, out, _ = run("--db", db, "ingest", str(SAMPLES))
        self.assertEqual(code, 0)
        code, out, _ = run("--db", db, "--as-of", "2026-10-22", "list", "--status", "overdue", "--json")
        rows = json.loads(out)
        self.assertGreater(len(rows), 10)
        self.assertTrue(all(r["status"] == "overdue" and r["days_overdue"] > 0 for r in rows))


if __name__ == "__main__":
    unittest.main()
