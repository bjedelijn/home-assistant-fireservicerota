"""Static regression guard for the development-only cache diagnostic service.

The service must remain a read-only inspection of already cached data.
These checks do not call BrandweerRooster or require live credentials.
"""

import ast
from pathlib import Path

from custom_components.fireservicerota.fairness_roster_scope import (
    assess_candidate_roster_source,
)


ROOT = Path(__file__).resolve().parents[1]
INIT_PATH = ROOT / "custom_components" / "fireservicerota" / "__init__.py"
SERVICE_YAML = ROOT / "custom_components" / "fireservicerota" / "services.yaml"


def _handler():
    module = ast.parse(INIT_PATH.read_text(encoding="utf-8"))
    handlers = [
        node for node in ast.walk(module)
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "async_inspect_fairness_roster_scope"
    ]
    assert len(handlers) == 1
    return handlers[0]


def test_roster_scope_handler_only_calls_approved_local_operations():
    handler = _handler()
    allowed = {
        "_service_entry_data",
        "_history_station",
        "assess_candidate_roster_source",
        "call.data.get",
    }
    names = set()
    for node in ast.walk(handler):
        if isinstance(node, ast.Call):
            names.add(ast.unparse(node.func))
        if isinstance(node, (ast.Await, ast.Yield, ast.YieldFrom)):
            raise AssertionError("Cache-only handler may not await external I/O")
    assert names == allowed


def test_roster_scope_handler_only_passes_cached_fields():
    handler = _handler()
    inspectors = [
        node for node in ast.walk(handler)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "assess_candidate_roster_source"
    ]
    assert len(inspectors) == 1
    keyword_sources = {
        key.arg: ast.unparse(key.value) for key in inspectors[0].keywords
    }
    assert keyword_sources == {
        "groups": "client.groups",
        "own_membership_index": "client.membership_index",
        "own_membership_duty": "client.membership_duty",
    }


def test_scope_service_is_response_only_and_described_as_cache_only():
    source = INIT_PATH.read_text(encoding="utf-8")
    reg = source.split(
        "if not hass.services.has_service(DOMAIN, SERVICE_INSPECT_FAIRNESS_ROSTER_SCOPE):",
        1,
    )[1].split(
        "if not hass.services.has_service(DOMAIN, SERVICE_PROBE_FAIRNESS_AVAILABILITY):",
        1,
    )[0]
    assert "supports_response=SupportsResponse.ONLY" in reg
    assert "schema=INSPECT_FAIRNESS_ROSTER_SCOPE_SCHEMA" in reg
    definition = SERVICE_YAML.read_text(encoding="utf-8").split(
        "\ninspect_fairness_roster_scope:\n", 1
    )[1]
    assert "No new BrandweerRooster API calls" in definition
    assert "station_id:" in definition


def test_diagnostic_output_is_aggregate_only_and_never_operational():
    result = assess_candidate_roster_source(
        194,
        groups=[{"id": 194, "type": "station", "memberships": [
            {"id": 999, "user_id": 1234567, "name": "PRIVATE SECRET",
             "status": "active"},
        ]}],
        own_membership_index={}, own_membership_duty={},
    )
    assert "PRIVATE SECRET" not in str(result)
    assert "1234567" not in str(result)
    assert "999" not in str(result)
    assert result["can_build_operational_prediction"] is False
    assert result["predicted_lineup"] is None
