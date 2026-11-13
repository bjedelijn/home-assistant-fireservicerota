"""Offline-only roster diagnostic runner, using synthetic anonymous fixtures."""

import ast
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_fairness_roster_scope_offline.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("fairness_scope_runner", SCRIPT)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def test_offline_runner_returns_only_aggregate_counts(tmp_path):
    payload = {
        "groups": [{"id": 194, "type": "station", "memberships": [
            {"id": 11, "user_id": 555321, "status": "active",
             "name": "PRIVATE NAME"},
        ]}],
        "own_membership_index": {"11": {}},
        "own_membership_duty": {"11": {}},
    }
    source = tmp_path / "private_fixture.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    result = _load_runner().inspect_offline(source, 194)
    assert result["cached_active_direct_station_membership_count"] == 1
    assert result["can_build_operational_prediction"] is False
    assert "PRIVATE NAME" not in str(result)
    assert "555321" not in str(result)


def test_offline_runner_rejects_unknown_input_keys(tmp_path):
    source = tmp_path / "fixture.json"
    source.write_text(json.dumps({
        "groups": [],
        "own_membership_index": {},
        "own_membership_duty": {},
        "token": "PRIVATE TOKEN",
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="Unexpected input keys"):
        _load_runner().inspect_offline(source, 194)


def test_offline_runner_rejects_large_files(tmp_path):
    source = tmp_path / "oversized.json"
    source.write_text("x" * 2_000_001, encoding="utf-8")
    with pytest.raises(ValueError, match="size limit"):
        _load_runner().inspect_offline(source, 194)


def test_offline_runner_makes_no_http_or_api_calls():
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = [
        alias.name for node in ast.walk(tree)
        if isinstance(node, ast.Import) for alias in node.names
    ]
    assert set(imports) == {"argparse", "importlib.util", "json"}
    assert not any(
        isinstance(node, ast.ImportFrom) and node.module in {
            "requests", "aiohttp", "urllib", "socket",
        }
        for node in ast.walk(tree)
    )
    assert "https://" not in source
    assert "async_api_get" not in source
