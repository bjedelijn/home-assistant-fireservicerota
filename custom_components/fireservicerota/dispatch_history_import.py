"""Conservative BWR incident-list conversion for private archive.

Only the numeric id and timezone-aware created_at are confirmed on the
historical listing probe. No guessed station, priority, vehicle or turnout.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def normalize_listing_page(payload: Any) -> list[dict]:
    """Accept only bounded known shapes; never retain original BWR payload."""
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
        rows = payload["data"]
    else:
        raise ValueError("Unexpected BWR listing response")
    if len(rows) > 25:
        raise ValueError("BWR exceeded bounded page size")
    seen: set[str] = set()
    output: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Unexpected BWR incident record")
        raw_id = row.get("id")
        raw_date = row.get("created_at")
        if isinstance(raw_id, bool) or not isinstance(raw_id, (str, int)):
            raise ValueError("Missing BWR incident identifier")
        ident = str(raw_id)
        if not ident.isdecimal() or len(ident) > 24 or ident in seen:
            raise ValueError("Invalid or repeated incident identifier")
        if not isinstance(raw_date, str) or len(raw_date) > 50:
            raise ValueError("Missing BWR incident timestamp")
        try:
            dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Invalid BWR incident timestamp") from exc
        if dt.tzinfo is None:
            raise ValueError("Incident timestamp must include timezone")
        seen.add(ident)
        output.append({"incident_id": ident, "occurred_at": dt.isoformat()})
    return output
