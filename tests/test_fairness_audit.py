"""Regression coverage for the read-only audit report parser."""
import asyncio

import pytest

from custom_components.fireservicerota.fairness_audit import analyze_incident_fairness


def row(time, subject, changes, whodunnit=None):
    return {
        "created_at": {"value": time},
        "audit_log_subject": {"value": subject},
        "changes": {"value": changes},
        "whodunnit": {"value": whodunnit},
    }


def test_suggestion_distinct_from_reported_turnout():
    suggestion = (
        "Suggestion based on fairness\n\n"
        "Person Alpha                   Aspirant Manschap\n"
        "Person Beta                    Chauffeur"
    )
    calls = []

    async def get(endpoint, params):
        calls.append((endpoint, params))
        if endpoint.endswith("/data"):
            if params.get("page", 1) > 1:
                return []
            return [
                row("2026-10-19T12:00:02+02:00", "Incident", suggestion),
                row("2026-10-19T12:00:01+02:00", "Opkomstbevestiging Person Alpha",
                    "Werkelijke opkomststatus is gewijzigd van Onbekend naar Uitgerukt"),
            ]
        return {
            "incident_responses": [
                {"user_id": 42, "user_name": "Person Alpha",
                 "status": "acknowledged", "reported_status": "dispatched"}
            ],
            "incident_skill_assignments": [],
        }

    result = asyncio.run(analyze_incident_fairness(get, 1234))
    assert result["audit_complete"] is True
    assert result["fairness_suggestion_count"] == 1
    assert result["latest_fairness_suggestion"]["members"][0] == {
        "name": "Person Alpha", "role": "Aspirant Manschap"
    }
    assert len(result["audit_turnout_status_changes"]) == 1
    assert result["api_snapshot"]["responses"][0]["reported_status"] == "dispatched"
    assert "not independent proof" in result["caution"]
    assert all(call[1] is None or call[1]["order"] == "desc" for call in calls)


def test_paginated_audit_recognizes_incomplete_results():
    async def get(endpoint, params):
        if endpoint.endswith("/data"):
            return [row(f"2026-10-19T12:00:{i:02d}+02:00", "Incident", "")
                    for i in range(100)]
        return {}

    result = asyncio.run(analyze_incident_fairness(get, 123, max_pages=1))
    assert result["audit_complete"] is False
    assert result["audit_pages_fetched"] == 1


def test_pagination_rejects_repeated_page():
    async def get(endpoint, params):
        if endpoint.endswith("/data"):
            return [row(f"2026-10-19T12:00:{i:02d}+02:00", "Incident", "")
                    for i in range(100)]
        return {}

    result = asyncio.run(analyze_incident_fairness(get, 123, max_pages=2))
    assert result["audit_complete"] is False
    assert "repeated" in result["audit_pagination_warning"]
    assert result["audit_records"] == 100


def test_reject_invalid_incident_id_and_page_count():
    async def get(endpoint, params):
        return []

    with pytest.raises(ValueError):
        asyncio.run(analyze_incident_fairness(get, "123/../../etc"))
    with pytest.raises(ValueError):
        asyncio.run(analyze_incident_fairness(get, 123, max_pages=21))


def test_non_json_error_is_not_mistaken_for_no_history():
    async def get(endpoint, params):
        return None

    with pytest.raises(ValueError, match="JSON list"):
        asyncio.run(analyze_incident_fairness(get, 1234))


def test_short_page_does_not_imply_complete_history():
    seen = []

    async def get(endpoint, params):
        if endpoint.endswith("/data"):
            page = params.get("page", 1)
            seen.append(page)
            if page == 1:
                return [row("2026-10-19T12:00:02+02:00", "Incident", "A")]
            if page == 2:
                return [row("2026-10-19T12:00:01+02:00", "Incident", "B")]
            return []
        return {}

    result = asyncio.run(analyze_incident_fairness(get, 123))
    assert seen == [1, 2, 3]
    assert result["audit_records"] == 2
    assert result["audit_complete"] is True
    assert result["audit_pagination_warning"] is None


def test_one_short_page_is_not_claimed_complete_at_limit():
    async def get(endpoint, params):
        if endpoint.endswith("/data"):
            return [row("2026-10-19T12:00:02+02:00", "Incident", "")]
        return {}

    result = asyncio.run(analyze_incident_fairness(get, 123, max_pages=1))
    assert result["audit_complete"] is False
    assert "limit reached" in result["audit_pagination_warning"]


def test_all_roles_are_analyzed_independently_including_commanders():
    first = (
        "Suggestion based on fairness\n"
        "Person One                    Bevelvoerder\n"
        "Person Two                    Chauffeur\n"
        "Person Three                  Manschap\n"
        "Person Four                   Aspirant Manschap"
    )
    second = (
        "Suggestion based on fairness\n"
        "Person Five                   Bevelvoerder\n"
        "Person One                    Chauffeur\n"
        "Person Three                  Manschap\n"
        "Person Four                   Aspirant Manschap"
    )

    async def get(endpoint, params):
        if endpoint.endswith("/data"):
            if params.get("page", 1) > 1:
                return []
            return [
                row("2026-10-19T12:00:02+02:00", "Incident", second),
                row("2026-10-19T12:00:01+02:00", "Incident", first),
            ]
        return {"incident_responses": [], "incident_skill_assignments": []}

    result = asyncio.run(analyze_incident_fairness(get, 1234))
    roles = {item["role"]: item for item in result["fairness_by_role"]}
    assert set(roles) == {
        "Bevelvoerder", "Chauffeur", "Manschap", "Aspirant Manschap"
    }
    assert roles["Bevelvoerder"]["latest_proposed_people"] == ["Person Five"]
    assert roles["Bevelvoerder"]["unique_proposed_people"] == 2
    assert roles["Chauffeur"]["latest_proposed_people"] == ["Person One"]
    assert roles["Manschap"]["proposed_seat_appearances"] == 2
    assert roles["Manschap"]["people"] == [
        {"name": "Person Three", "proposed_in_suggestions": 2}
    ]
    assert roles["Aspirant Manschap"]["unique_proposed_people"] == 1
    # The same person can occupy different functions across proposals.
    assert {p["name"] for p in roles["Bevelvoerder"]["people"]} == {
        "Person One", "Person Five"
    }
    assert {p["name"] for p in roles["Chauffeur"]["people"]} == {
        "Person One", "Person Two"
    }
