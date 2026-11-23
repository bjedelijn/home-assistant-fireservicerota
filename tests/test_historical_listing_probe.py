"""Synthetic listing capability tests; no live incident or station records."""
from custom_components.fireservicerota.historical_listing_probe import summarize_history_listing, compare_history_listing_pages, summarize_history_listing_scan


def test_list_metadata_never_exposes_private_data():
    result = summarize_history_listing([
        {
            "id": "SYNTHETIC_SECRET_INCIDENT",
            "created_at": "2024-02-01T12:00:00+01:00",
            "description": "SYNTHETIC_SECRET_PERSON",
            "station": "SYNTHETIC_SECRET_STATION",
        },
        {
            "id": "SYNTHETIC_SECRET_INCIDENT_2",
            "created_at": "2023-02-01T12:00:00+01:00",
        },
    ])
    assert result["status"] == "listing_shape_observed"
    assert result["items_inspected"] == 2
    assert result["earliest_visible_at"] == "2023-02-01T12:00:00+01:00"
    assert result["date_filter_supported"] is None
    assert result["history_complete"] is False
    assert "SYNTHETIC_SECRET" not in str(result)


def test_rejects_unrecognized_and_large_payloads():
    assert summarize_history_listing({"other": []})["status"] == "unrecognized_listing_shape"
    assert summarize_history_listing([{}] * 51)["status"] == "response_exceeded_probe_limit"


def test_data_envelope_and_invalid_source_date():
    result = summarize_history_listing({"data": [
        {"created_at": "SYNTHETIC_PRIVATE_DATE"},
    ]})
    assert result["items_inspected"] == 1
    assert result["earliest_visible_at"] is None
    assert "SYNTHETIC_PRIVATE_DATE" not in str(result)


def test_distinct_pages_are_compared_without_echoing_ids():
    first = [
        {"id": 101, "created_at": "2025-05-02T10:00:00+02:00",
         "description": "SYNTHETIC_PRIVATE_PERSON"},
        {"id": 102, "created_at": "2025-05-01T10:00:00+02:00"},
    ]
    second = [
        {"id": 103, "created_at": "2025-04-30T10:00:00+02:00"},
        {"id": 104, "created_at": "2025-04-29T10:00:00+02:00"},
    ]
    result = compare_history_listing_pages(first, second)
    assert result["pagination_verified"] is True
    assert result["page_2_older_than_page_1"] is True
    assert result["distinct_incident_count"] == 4
    assert result["overlapping_incident_count"] == 0
    assert "SYNTHETIC_PRIVATE_PERSON" not in str(result)
    assert result["history_complete"] is False


def test_repeated_page_is_not_pagination_proof():
    page = [{"id": 201, "created_at": "2025-05-02T10:00:00+02:00"}]
    result = compare_history_listing_pages(page, page)
    assert result["status"] == "repeated_or_overlapping_pages"
    assert result["pagination_verified"] is False


def test_empty_page_is_not_claimed_complete_archive():
    page = [{"id": 202, "created_at": "2025-05-02T10:00:00+02:00"}]
    result = compare_history_listing_pages(page, [])
    assert result["status"] == "second_page_empty"
    assert result["history_complete"] is False


def test_non_numeric_identifier_is_not_echoed():
    result = compare_history_listing_pages(
        [{"id": "SYNTHETIC_SECRET_ID"}], [{"id": 203}]
    )
    assert result["status"] == "identifiers_not_comparable"
    assert "SYNTHETIC_SECRET_ID" not in str(result)


def test_five_page_scan_reports_counts_and_privacy():
    pages = [
        [
            {
                "id": 500 + page * 10 + item,
                "created_at": f"2025-01-{20-page:02d}T12:00:00+01:00",
                "person": "SYNTHETIC_SECRET_PERSON",
            }
            for item in range(3)
        ]
        for page in range(5)
    ]
    result = summarize_history_listing_scan(pages)
    assert result["status"] == "distinct_pages_observed"
    assert result["pages_requested"] == 5
    assert result["total_items_observed"] == 15
    assert result["distinct_incident_count"] == 15
    assert result["overlapping_incident_count"] == 0
    assert result["per_page_requested"] == 25
    assert result["history_complete"] is False
    assert "SYNTHETIC_SECRET" not in str(result)


def test_scan_rejects_duplicate_incident_identifiers():
    pages = [
        [{"id": 701, "created_at": "2025-01-01T10:00:00+01:00"}],
        [{"id": 701, "created_at": "2024-01-01T10:00:00+01:00"}],
    ]
    result = summarize_history_listing_scan(pages)
    assert result["pagination_verified"] is False
    assert result["overlapping_incident_count"] == 1


def test_scan_never_claims_full_history_on_empty_page():
    result = summarize_history_listing_scan([
        [{"id": 701}], []
    ])
    assert result["history_complete"] is False
    assert result["pagination_verified"] is False


def test_unrecognized_page_stops_scan_without_claiming_end_of_history():
    result = summarize_history_listing_scan([
        [{"id": 812, "created_at": "2025-04-01T08:00:00+02:00"}],
        {"error": "SYNTHETIC_PRIVATE_ERROR"},
    ])
    assert result["status"] == "unrecognized_page_shape"
    assert result["stopped_on_unexpected_response"] is True
    assert result["history_complete"] is False
    assert "SYNTHETIC_PRIVATE_ERROR" not in str(result)
