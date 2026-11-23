"""Synthetic BWR-primary/P2000-fallback policy checks. No live API."""
from custom_components.fireservicerota.historical_source_merge import merge_bwr_p2000


def test_bwr_is_leading_and_p2000_fills_only_missing_fields():
    bwr = [{"incident_id": "10", "title": "BWR report",
            "priority": 1, "station_key": "TEST_STATION",
            "responder_names": ["PRIVATE_FIXTURE"]}]
    p2000 = [{"event_id": "80", "title": "Different radio text",
              "priority": 2, "vehicle_keys": ["TEST_UNIT"],
              "people": ["PRIVATE_FIXTURE"]}]
    result = merge_bwr_p2000(bwr, p2000, verified_links={"80": "10"})
    assert result["summary"]["bwr_incidents"] == 1
    assert result["summary"]["verified_linked_p2000_events"] == 1
    assert len(result["records"]) == 1
    record = result["records"][0]
    assert record["fields"]["title"] == "BWR report"
    assert record["fields"]["priority"] == 1
    assert record["fields"]["vehicle_keys"] == ["TEST_UNIT"]
    assert record["field_sources"]["title"] == "bwr"
    assert record["field_sources"]["vehicle_keys"] == "p2000"
    assert set(record["conflicting_fields"]) == {"title", "priority"}
    assert record["fairness_source"] == "bwr_only"
    assert "PRIVATE_FIXTURE" not in str(result)


def test_p2000_alone_never_creates_fairness_and_never_automatches():
    result = merge_bwr_p2000(
        [{"incident_id": "10", "title": "Same synthetic title"}],
        [{"event_id": "80", "title": "Same synthetic title", "priority": 1}],
    )
    assert result["summary"]["bwr_incidents"] == 1
    assert result["summary"]["p2000_only_incidents"] == 1
    assert result["summary"]["verified_linked_p2000_events"] == 0
    alone = next(row for row in result["records"] if row["primary_source"] == "p2000")
    assert alone["fairness_source"] == "none"


def test_unresolved_link_never_silently_merges_or_drops_event():
    result = merge_bwr_p2000(
        [{"incident_id": "10"}], [{"event_id": "80", "priority": 1}],
        verified_links={"80": "999"},
    )
    assert result["summary"]["rejected_or_unresolved_links"] == 1
    assert result["summary"]["p2000_only_incidents"] == 1
    assert len(result["records"]) == 2


def test_source_dedup_and_rejected_unexpected_payload():
    result = merge_bwr_p2000(
        [{"incident_id": "10"}, {"incident_id": "10"}, {"incident_id": True}],
        [{"event_id": "80"}, {"event_id": "80"}, {"event_id": False}],
    )
    assert len(result["records"]) == 2
    assert result["summary"]["skipped_duplicate_or_invalid_records"] == 4


def test_multiple_verified_alerts_one_bwr_incident():
    result = merge_bwr_p2000(
        [{"incident_id": "10"}],
        [{"event_id": "80", "vehicle_keys": ["UNIT_1"]},
         {"event_id": "81", "station_key": "TEST_STATION"}],
        verified_links={"80": "10", "81": "10"},
    )
    assert len(result["records"]) == 1
    record = result["records"][0]
    assert record["linked_p2000_events"] == 2
    assert record["fields"]["vehicle_keys"] == ["UNIT_1"]
    assert record["fields"]["station_key"] == "TEST_STATION"
