"""Spec ING-06, ING-07, ING-08."""
import unittest

from actiontrack.people import Roster, split_owner

R = Roster()
R.add(["Priya Nair", "Priya Shah", "Rahul Mehta", "Rahul Verma", "Sam Okafor", "Anita Desai"])


class Split(unittest.TestCase):
    def test_forms_ING_06(self):
        self.assertEqual(split_owner("Priya to send the slides"), (["Priya"], "send the slides"))
        self.assertEqual(split_owner("@anita: audit contrast"), (["anita"], "audit contrast"))
        self.assertEqual(split_owner("Sam: share the guide"), (["Sam"], "share the guide"))
        self.assertEqual(split_owner("Anita & Rahul to agree on the API")[0], ["Anita", "Rahul"])
        self.assertEqual(split_owner("Anita and Rahul to agree")[0], ["Anita", "Rahul"])
        self.assertEqual(split_owner("Priya N. to send the quote")[0], ["Priya N."])
        owners, task = split_owner("Lena (with Priya) to collect feedback")
        self.assertEqual(owners, ["Lena"])
        self.assertIn("(with Priya)", task)

    def test_no_owner_ING_06(self):
        self.assertEqual(split_owner("book the venue"), ([], "book the venue"))
        self.assertEqual(split_owner("Update the docs to reflect changes")[0], [])


class Resolve(unittest.TestCase):
    def test_unique_first_name_ING_07(self):
        o = R.resolve("Sam", [])
        self.assertEqual((o.state, o.name), ("resolved", "Sam Okafor"))

    def test_attendees_disambiguate_ING_07(self):
        o = R.resolve("Priya", ["Priya Shah", "Sam Okafor"])
        self.assertEqual((o.state, o.name), ("resolved", "Priya Shah"))

    def test_both_present_is_ambiguous_ING_07(self):
        o = R.resolve("Rahul", ["Rahul Mehta", "Rahul Verma"])
        self.assertEqual(o.state, "ambiguous")
        self.assertEqual(o.candidates, ["Rahul Mehta", "Rahul Verma"])
        self.assertIsNone(o.name)

    def test_no_attendees_falls_back_to_roster_ING_07(self):
        self.assertEqual(R.resolve("Rahul", []).state, "ambiguous")

    def test_initial_narrows_ING_07(self):
        o = R.resolve("Priya N.", ["Priya Nair", "Priya Shah"])
        self.assertEqual(o.name, "Priya Nair")
        o = R.resolve("Priya S.", [])
        self.assertEqual(o.name, "Priya Shah")

    def test_unknown_person_kept_ING_07(self):
        o = R.resolve("Zoe", [])
        self.assertEqual((o.state, o.name), ("resolved", "Zoe"))

    def test_group_and_none_ING_08(self):
        self.assertEqual(R.resolve("Everyone", []).state, "group")
        self.assertEqual(R.resolve("Team", []).state, "group")
        self.assertEqual(R.resolve("TBD", []).state, "none")
        self.assertEqual(R.resolve("Someone", []).state, "none")


class FindPerson(unittest.TestCase):
    def test_whole_words_only_FUP_01(self):
        self.assertEqual(R.find_person("Sam"), ["Sam Okafor"])
        self.assertEqual(R.find_person("okafor"), ["Sam Okafor"])
        self.assertEqual(R.find_person("priya shah"), ["Priya Shah"])
        self.assertEqual(R.find_person("Priya"), ["Priya Nair", "Priya Shah"])
        for fragment in ("ok", "okaf", "an", "ra", "sa", ""):
            self.assertEqual(R.find_person(fragment), [], fragment)


if __name__ == "__main__":
    unittest.main()
