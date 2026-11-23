"""Synthetic proposal-only tests. No real posts, incidents or member identifiers."""
from custom_components.fireservicerota.fairness_revision_summary import summarize_proposal_revisions


def _audit(*snapshots, complete=True):
    return {
        "audit_complete": complete,
        "fairness_suggestions": [
            {"at": f"2024-01-01T12:00:{i:02d}+00:00",
             "members": [{"name": name, "role": role} for name, role in rows]}
            for i, rows in enumerate(snapshots)
        ],
    }


def test_revisions_count_changes_without_leaking_names():
    result = summarize_proposal_revisions(
        _audit([("SYNTH_PERSON_A", "Bevelvoerder"), ("SYNTH_PERSON_B", "Chauffeur")],
               [("SYNTH_PERSON_A", "Bevelvoerder"), ("SYNTH_PERSON_C", "Chauffeur")],
               [("SYNTH_PERSON_D", "Bevelvoerder"), ("SYNTH_PERSON_C", "Chauffeur")])
    )
    assert result["comparison_status"] == "textual_snapshots_compared"
    assert result["proposal_snapshots_seen"] == 3
    assert result["distinct_revisions"] == 2
    assert result["added_role_assignments"] == 2
    assert result["removed_role_assignments"] == 2
    assert result["initial_role_counts"] == [
        {"role": "Bevelvoerder", "proposed_seats": 1},
        {"role": "Chauffeur", "proposed_seats": 1},
    ]
    assert "SYNTH_PERSON" not in str(result)
    assert "members" not in str(result)


def test_incomplete_audit_never_claims_reliable_comparison():
    result = summarize_proposal_revisions(
        _audit([("SYNTH_PERSON_A", "Bevelvoerder")], complete=False)
    )
    assert result["comparison_status"] == "audit_incomplete"
    assert result["added_role_assignments"] is None


def test_identical_snapshots_are_not_revisions():
    rows = [("SYNTH_PERSON_A", "Bevelvoerder")]
    result = summarize_proposal_revisions(_audit(rows, rows))
    assert result["distinct_revisions"] == 0
    assert result["added_role_assignments"] == 0


def test_malformed_entries_do_not_escape():
    result = summarize_proposal_revisions({
        "audit_complete": True,
        "fairness_suggestions": [{"at": "2024-01-01", "members": [
            {"name": {"secret": "PRIVATE"}, "role": "Bevelvoerder"}
        ]}],
    })
    assert result["comparison_status"] == "invalid_proposal_members"
    assert "PRIVATE" not in str(result)


def test_no_proposals_preserves_uncertainty():
    result = summarize_proposal_revisions(_audit())
    assert result["comparison_status"] == "no_proposals_or_limit_exceeded"
    assert result["selection_reason_verified"] is False
    assert result["physical_vehicle_crew_verified"] is False


def test_revision_timeline_and_per_role_counts_are_anonymous():
    result = summarize_proposal_revisions(
        _audit(
            [("SYNTH_PERSON_A", "Bevelvoerder"), ("SYNTH_PERSON_B", "Chauffeur")],
            [("SYNTH_PERSON_A", "Bevelvoerder"), ("SYNTH_PERSON_C", "Chauffeur")],
            [("SYNTH_PERSON_D", "Bevelvoerder"), ("SYNTH_PERSON_C", "Chauffeur")],
        )
    )
    assert result["net_role_assignment_changes"] == [
        {"role": "Bevelvoerder", "added_role_assignments": 1, "removed_role_assignments": 1},
        {"role": "Chauffeur", "added_role_assignments": 1, "removed_role_assignments": 1},
    ]
    assert result["transition_role_change_totals"] == [
        {"role": "Bevelvoerder", "added_role_assignments": 1, "removed_role_assignments": 1},
        {"role": "Chauffeur", "added_role_assignments": 1, "removed_role_assignments": 1},
    ]
    assert result["revision_timeline"] == [
        {"proposal_index": 2, "at": "2024-01-01T12:00:01+00:00",
         "changes_by_role": [{"role": "Chauffeur",
                              "added_role_assignments": 1,
                              "removed_role_assignments": 1}]},
        {"proposal_index": 3, "at": "2024-01-01T12:00:02+00:00",
         "changes_by_role": [{"role": "Bevelvoerder",
                              "added_role_assignments": 1,
                              "removed_role_assignments": 1}]},
    ]
    assert "SYNTH_PERSON" not in str(result)


def test_transient_swap_is_counted_but_net_change_zero():
    result = summarize_proposal_revisions(
        _audit(
            [("SYNTH_PERSON_A", "Bevelvoerder")],
            [("SYNTH_PERSON_B", "Bevelvoerder")],
            [("SYNTH_PERSON_A", "Bevelvoerder")],
        )
    )
    assert result["distinct_revisions"] == 2
    assert result["added_role_assignments"] == 0
    assert result["removed_role_assignments"] == 0
    assert result["net_role_assignment_changes"] == []
    assert result["transition_role_change_totals"] == [
        {"role": "Bevelvoerder", "added_role_assignments": 2, "removed_role_assignments": 2}
    ]


def test_malformed_timestamp_is_not_echoed():
    result = summarize_proposal_revisions({
        "audit_complete": True,
        "fairness_suggestions": [{"at": "SECRET_TIMESTAMP_CONTENT", "members": [
            {"name": "SYNTH_PERSON_A", "role": "Bevelvoerder"}
        ]}],
    })
    assert result["comparison_status"] == "invalid_proposal_timestamp"
    assert "SECRET_TIMESTAMP_CONTENT" not in str(result)


def test_confidential_free_text_role_is_collapsed_to_overig():
    private_role = "SYNTHETIC_PRIVATE_STATION_UNIT_X9"
    result = summarize_proposal_revisions(
        _audit(
            [("SYNTH_PERSON_A", private_role), ("SYNTH_PERSON_B", "Other secret duty")],
            [("SYNTH_PERSON_C", private_role), ("SYNTH_PERSON_B", "Other secret duty")],
        )
    )
    assert result["comparison_status"] == "textual_snapshots_compared"
    assert result["initial_role_counts"] == [{"role": "overig", "proposed_seats": 2}]
    assert result["latest_role_counts"] == [{"role": "overig", "proposed_seats": 2}]
    assert result["net_role_assignment_changes"] == [
        {"role": "overig", "added_role_assignments": 1, "removed_role_assignments": 1}
    ]
    assert result["transition_role_change_totals"] == [
        {"role": "overig", "added_role_assignments": 1, "removed_role_assignments": 1}
    ]
    assert result["revision_timeline"][0]["changes_by_role"] == [
        {"role": "overig", "added_role_assignments": 1, "removed_role_assignments": 1}
    ]
    assert private_role not in str(result)
    assert "secret duty" not in str(result)


def test_untrusted_near_match_must_not_be_whitelisted():
    result = summarize_proposal_revisions(
        _audit([("SYNTH_PERSON_A", "Bevelvoerder - synthetic private station")])
    )
    assert result["initial_role_counts"] == [{"role": "overig", "proposed_seats": 1}]
    assert "synthetic private station" not in str(result)
