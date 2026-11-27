"""Synthetic schedules for bounded retrospective checking; no real identities."""
from datetime import datetime, timedelta, timezone

from custom_components.fireservicerota.turnout_recheck_selection import select_turnout_rechecks


NOW = datetime(2025, 2, 20, 12, tzinfo=timezone.utc)


def _row(identifier, age_days, checked_days_ago=None):
    row = {
        "incident_id": str(identifier),
        "latest_proposal_at": (NOW - timedelta(days=age_days)).isoformat(),
    }
    if checked_days_ago is not None:
        row["turnout_audit_review"] = {
            "checked_at": (NOW - timedelta(days=checked_days_ago)).isoformat()
        }
    return row


def test_daily_due_for_recent_incidents():
    rows = [_row("111", 3, 0.5), _row("222", 3, 1.5)]
    selected = select_turnout_rechecks(rows, NOW)
    assert [item["incident_id"] for item in selected] == ["222"]


def test_weekly_after_two_weeks():
    rows = [_row("111", 20, 3), _row("222", 20, 8)]
    selected = select_turnout_rechecks(rows, NOW)
    assert [item["incident_id"] for item in selected] == ["222"]


def test_excludes_new_and_old_incidents():
    rows = [_row("111", 0.2), _row("222", 46), _row("333", 15)]
    selected = select_turnout_rechecks(rows, NOW)
    assert [item["incident_id"] for item in selected] == ["333"]


def test_bounded_prioritization_without_network_calls():
    selected = select_turnout_rechecks(
        [_row(str(100 + n), 2 + n) for n in range(9)], NOW, limit=2
    )
    assert len(selected) == 2
    assert [item["incident_id"] for item in selected] == ["108", "107"]


def test_malformed_dates_and_ids_skipped():
    rows = [
        {"incident_id": "SYNTHETIC_PERSON", "latest_proposal_at": NOW.isoformat()},
        {"incident_id": "123", "latest_proposal_at": "PRIVATE_INVALID_DATE"},
        _row("456", 2),
    ]
    assert [row["incident_id"] for row in select_turnout_rechecks(rows, NOW)] == ["456"]
