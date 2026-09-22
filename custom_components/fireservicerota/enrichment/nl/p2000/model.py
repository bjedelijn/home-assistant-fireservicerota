"""Normalized P2000 data model used by all providers."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class P2000Event:
    """One normalized P2000 alert."""

    source: str
    external_id: str | None
    event_time: str | None
    received_at: str
    message: str
    human_message: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    city: str | None = None
    street: str | None = None
    postcode: str | None = None
    priority: int | None = None
    grip: int | None = None
    capcodes: list[dict[str, Any]] = field(default_factory=list)
    units: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON/RestoreEntity-friendly representation."""
        return asdict(self)
