"""Only synthetic turnout audit records; never operational user or post data."""
from custom_components.fireservicerota.turnout_audit_summary import summarize_turnout_audit


def _audit(events, proposals=None, complete=True):
    return {
        "audit_complete": complete,
        "audit_turnout_status_changes": events,
        "fairness_suggestions": proposals if proposals is not None else [
            {"at": "2024-01-01T09:00:00+01:00", "members": []}
        ],
    }


def test_audit_markers_after_last_proposal_are_reported_without_identity():
    result = summarize_turnout_audit(_audit([
        {"at": "2024-01-01T08:59:00+01:00",
         "subject": "SYNTH_PERSON_PRIVATE", "changed_by": "SYNTH_MODERATOR",
         "description": "Werkelijke opkomststatus: SYNTHETIC_PRIVATE"},
        {"at": "2024-01-08T10:00:00+01:00",
         "subject": "SYNTH_PERSON_PRIVATE", "changed_by": "SYNTH_MODERATOR",
         "description": "Werkelijke opkomststatus: SYNTHETIC_PRIVATE"},
    ]))
    assert result["turnout_status_audit_events_seen"] == 2
    assert result["events_after_last_fairness_proposal"] == 1
    assert result["first_turnout_status_event_at"] == "2024-01-01T08:59:00+01:00"
    assert result["latest_turnout_status_event_at"] == "2024-01-08T10:00:00+01:00"
    assert result["manual_corrections_verified"] is False
    assert result["old_new_status_values_verified"] is False
    text = str(result)
    for secret in ("SYNTH_PERSON_PRIVATE", "SYNTH_MODERATOR", "SYNTHETIC_PRIVATE"):
        assert secret not in text


def test_no_status_events_does_not_claim_manual_change():
    result = summarize_turnout_audit(_audit([]))
    assert result["comparison_status"] == "audit_markers_observed"
    assert result["turnout_status_audit_timeline"] == []
    assert result["turnout_status_audit_events_seen"] == 0
    assert result["manual_corrections_verified"] is False


def test_unfinished_audit_cannot_be_interpreted_as_complete():
    result = summarize_turnout_audit(_audit([], complete=False))
    assert result["comparison_status"] == "audit_incomplete"
    assert result["events_after_last_fairness_proposal"] is None


def test_invalid_time_is_never_echoed():
    result = summarize_turnout_audit(_audit([
        {"at": "SECRET_PRIVATE_TIME", "description": "SYNTHETIC_PRIVATE"}
    ]))
    assert result["comparison_status"] == "invalid_audit_timestamp"
    assert "SECRET_PRIVATE_TIME" not in str(result)


def test_offsets_compare_chronologically_not_as_strings():
    result = summarize_turnout_audit(_audit(
        [{"at": "2024-01-01T12:00:00+01:00"}],
        [{"at": "2024-01-01T11:30:00+00:00"}],
    ))
    assert result["events_after_last_fairness_proposal"] == 0
