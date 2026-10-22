"""Spec ING-03, ING-09."""
import unittest
from datetime import date

from actiontrack.dates import extract_due, parse_header_date

WED = date(2026, 9, 2)   # Wednesday
FRI = date(2026, 9, 4)   # Friday


def due(text, meeting=WED):
    return extract_due(text, meeting)[1]


class HeaderDates(unittest.TestCase):
    def test_formats_ING_03(self):
        self.assertEqual(parse_header_date("2026-09-01"), date(2026, 9, 1))
        self.assertEqual(parse_header_date("9 September 2026"), date(2026, 9, 9))
        self.assertEqual(parse_header_date("Monday, 14 September 2026"), date(2026, 9, 14))
        self.assertIsNone(parse_header_date("sometime last week"))


class DueDates(unittest.TestCase):
    def test_iso_and_day_month_ING_09(self):
        self.assertEqual(due("x by 2026-09-08"), date(2026, 9, 8))
        self.assertEqual(due("x by 25 Sep"), date(2026, 9, 25))
        self.assertEqual(due("x by Oct 3rd"), date(2026, 10, 3))
        self.assertEqual(due("x by Wed 16 Sep"), date(2026, 9, 16))
        self.assertEqual(due("x, results due 15 October"), date(2026, 10, 15))

    def test_bare_weekday_is_strictly_after_ING_09(self):
        self.assertEqual(due("x by Friday", WED), date(2026, 9, 4))
        self.assertEqual(due("x by Wednesday", WED), date(2026, 9, 9))  # same weekday -> next week
        self.assertEqual(due("x by Mon", FRI), date(2026, 9, 7))

    def test_next_weekday_is_following_week_ING_09(self):
        self.assertEqual(due("x by next Tuesday", WED), date(2026, 9, 8))
        self.assertEqual(due("x by next Tuesday", date(2026, 9, 1)), date(2026, 9, 8))  # Tue meeting

    def test_relative_words_ING_09(self):
        self.assertEqual(due("x by tomorrow"), date(2026, 9, 3))
        self.assertEqual(due("x by EOD"), WED)
        self.assertEqual(due("x by EOD tomorrow"), date(2026, 9, 3))
        self.assertEqual(due("circulate the summary tomorrow"), date(2026, 9, 3))
        self.assertEqual(due("x by end of month"), date(2026, 9, 30))
        self.assertEqual(due("x by end of next week"), date(2026, 9, 11))
        self.assertEqual(due("x by mid-October"), date(2026, 10, 15))

    def test_year_rollover_ING_09(self):
        self.assertEqual(due("x by 5 Jan", date(2026, 12, 20)), date(2027, 1, 5))

    def test_non_dates_ignored_ING_09(self):
        self.assertIsNone(due("cut costs by 10%"))
        self.assertIsNone(due("freeze invoices from 9 Oct"))     # 'from' is not a marker
        self.assertIsNone(due("schedule cutover for Saturday 10 Oct"))
        self.assertIsNone(due("review the doc"))

    def test_last_marker_wins_and_phrase_removed_ING_09(self):
        task, d, raw, _ = extract_due("cut cloud costs by 10% - proposal by 2026-09-09", WED)
        self.assertEqual(d, date(2026, 9, 9))
        self.assertEqual(raw, "2026-09-09")
        self.assertNotIn("2026", task)


if __name__ == "__main__":
    unittest.main()
