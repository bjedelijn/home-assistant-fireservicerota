"""Tests for schedule announcement helper without Home Assistant runtime."""
import importlib.util
from datetime import datetime
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo

MODULE = Path(__file__).resolve().parents[1] / "custom_components" / "fireservicerota" / "schedule_helpers.py"
spec = importlib.util.spec_from_file_location("schedule_helpers", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class NextAvailableTests(unittest.TestCase):
    def setUp(self):
        self.tz = ZoneInfo("Europe/Amsterdam")

    def moment(self, hour, day=7):
        return datetime(2026, 11, day, hour, tzinfo=self.tz)

    def interval(self, start, end, available):
        return {"start_time": start.isoformat(), "end_time": end.isoformat(), "available": available}

    def test_multiple_unavailable_blocks(self):
        boundary = self.moment(17)
        rows = [
            self.interval(self.moment(17), self.moment(20), False),
            self.interval(self.moment(20), self.moment(8, 8), False),
            self.interval(self.moment(8, 8), self.moment(12, 8), True),
        ]
        self.assertEqual(mod.next_available_after({"complete": True, "intervals": rows}, boundary), self.moment(8, 8))

    def test_already_available_at_override_end(self):
        boundary = self.moment(17)
        rows = [self.interval(self.moment(16), self.moment(20), True)]
        self.assertEqual(mod.next_available_after({"complete": True, "intervals": rows}, boundary), boundary)

    def test_missing_day_is_unknown(self):
        boundary = self.moment(17)
        rows = [self.interval(self.moment(17), self.moment(20), False),
                self.interval(self.moment(8, 8), self.moment(12, 8), True)]
        self.assertIsNone(mod.next_available_after({"complete": False, "intervals": rows}, boundary))
        self.assertIsNone(mod.next_available_after({"complete": True, "intervals": rows}, boundary))

    def test_conflicting_overlaps_do_not_announce_early(self):
        boundary = self.moment(17)
        rows = [self.interval(self.moment(17), self.moment(20), True),
                self.interval(self.moment(16), self.moment(19), False),
                self.interval(self.moment(19), self.moment(21), True)]
        self.assertEqual(mod.next_available_after({"complete": True, "intervals": rows}, boundary), self.moment(19))

    def test_invalid_availability_not_treated_as_true(self):
        boundary = self.moment(17)
        rows = [self.interval(self.moment(17), self.moment(20), "false")]
        self.assertIsNone(mod.next_available_after({"complete": True, "intervals": rows}, boundary))

    def test_dst_transition(self):
        tz = self.tz
        boundary = datetime(2027, 3, 28, 1, 0, tzinfo=tz)
        first_end = datetime(2027, 3, 28, 3, 0, tzinfo=tz)
        next_end = datetime(2027, 3, 28, 6, 0, tzinfo=tz)
        rows = [self.interval(boundary, first_end, False),
                self.interval(first_end, next_end, True)]
        self.assertEqual(mod.next_available_after({"complete": True, "intervals": rows}, boundary), first_end)


if __name__ == "__main__":
    unittest.main()
