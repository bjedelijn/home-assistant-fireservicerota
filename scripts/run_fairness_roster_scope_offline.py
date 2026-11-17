#!/usr/bin/env python3
"""Offline, no-network inspection of an explicitly supplied local JSON fixture.

Never commit real BrandweerRooster group payloads, member data or schedules.
Only fixed aggregate diagnostics go to stdout; input is never printed.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSPECTOR = (
    ROOT / "custom_components" / "fireservicerota" / "fairness_roster_scope.py"
)
MAX_INPUT_BYTES = 2_000_000


def inspect_offline(path: Path, station_id: int) -> dict:
    """Read one local JSON file; never connect to BrandweerRooster or HA."""
    if not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("Input must be a JSON file within the size limit")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {
        "groups", "own_membership_index", "own_membership_duty",
    }:
        raise ValueError("Unexpected input keys")
    spec = importlib.util.spec_from_file_location(
        "offline_fairness_roster_scope", INSPECTOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Inspector module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.assess_candidate_roster_source(
        station_id,
        groups=data["groups"],
        own_membership_index=data["own_membership_index"],
        own_membership_duty=data["own_membership_duty"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Offline, anonymous roster scope diagnostic (no API calls)"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--station-id", type=int, required=True)
    args = parser.parse_args()
    try:
        result = inspect_offline(args.input, args.station_id)
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError):
        parser.exit(2, "Offline inspection could not read a valid input file.\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
