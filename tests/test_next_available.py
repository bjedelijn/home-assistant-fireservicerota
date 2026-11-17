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


def test_next_unavailable_after_follows_contiguous_paraat_blocks():
    boundary = datetime(2026, 11, 17, 8, 30, tzinfo=ZoneInfo("Europe/Amsterdam"))
    middle = datetime(2026, 11, 17, 12, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
    final = datetime(2026, 11, 17, 17, 45, tzinfo=ZoneInfo("Europe/Amsterdam"))
    tomorrow = datetime(2026, 11, 18, 0, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
    schedule = {"complete": True, "intervals": [
        {"start_time": boundary.isoformat(), "end_time": middle.isoformat(), "available": True},
        {"start_time": middle.isoformat(), "end_time": final.isoformat(), "available": True},
        {"start_time": final.isoformat(), "end_time": tomorrow.isoformat(), "available": False},
    ]}
    assert mod.next_unavailable_after(schedule, boundary) == final


def test_next_unavailable_after_fails_closed_on_gap_or_incomplete_schedule():
    tz = ZoneInfo("Europe/Amsterdam")
    boundary = datetime(2026, 11, 17, 8, 30, tzinfo=tz)
    middle = datetime(2026, 11, 17, 12, 0, tzinfo=tz)
    evening = datetime(2026, 11, 17, 17, 45, tzinfo=tz)
    intervals = [
        {"start_time": boundary.isoformat(), "end_time": middle.isoformat(), "available": True},
        {"start_time": evening.isoformat(), "end_time": evening.replace(hour=18).isoformat(), "available": False},
    ]
    assert mod.next_unavailable_after({"complete": True, "intervals": intervals}, boundary) is None
    assert mod.next_unavailable_after({"complete": False, "intervals": intervals}, boundary) is None


def test_next_unavailable_after_rejects_conflicting_overlaps():
    tz = ZoneInfo("Europe/Amsterdam")
    boundary = datetime(2026, 11, 17, 8, 30, tzinfo=tz)
    later = datetime(2026, 11, 17, 12, 0, tzinfo=tz)
    rows = [
        {"start_time": boundary.isoformat(), "end_time": later.isoformat(), "available": True},
        {"start_time": boundary.isoformat(), "end_time": later.isoformat(), "available": False},
    ]
    assert mod.next_unavailable_after({"complete": True, "intervals": rows}, boundary) is None


def test_next_unavailable_after_returns_boundary_if_roster_immediately_not_paraat():
    tz = ZoneInfo("Europe/Amsterdam")
    boundary = datetime(2026, 11, 17, 8, 30, tzinfo=tz)
    later = datetime(2026, 11, 17, 12, 0, tzinfo=tz)
    rows = [{"start_time": boundary.isoformat(), "end_time": later.isoformat(), "available": False}]
    assert mod.next_unavailable_after({"complete": True, "intervals": rows}, boundary) == boundary


def test_next_unavailable_after_invalid_availability_never_guesses():
    tz = ZoneInfo("Europe/Amsterdam")
    boundary = datetime(2026, 11, 17, 8, 30, tzinfo=tz)
    later = datetime(2026, 11, 17, 12, 0, tzinfo=tz)
    rows = [{"start_time": boundary.isoformat(), "end_time": later.isoformat(), "available": "yes"}]
    assert mod.next_unavailable_after({"complete": True, "intervals": rows}, boundary) is None


def test_next_unavailable_after_rejects_conflict_starting_mid_paraat_block():
    tz = ZoneInfo("Europe/Amsterdam")
    morning = datetime(2026, 11, 17, 8, 30, tzinfo=tz)
    eleven = datetime(2026, 11, 17, 11, 0, tzinfo=tz)
    noon = datetime(2026, 11, 17, 12, 0, tzinfo=tz)
    rows = [
        {"start_time": morning.isoformat(), "end_time": noon.isoformat(),
         "available": True},
        {"start_time": eleven.isoformat(), "end_time": noon.isoformat(),
         "available": False},
    ]
    assert mod.next_unavailable_after({"complete": True, "intervals": rows}, morning) is None
