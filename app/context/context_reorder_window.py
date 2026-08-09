from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass
class ContextReorderWindowResult:
    stable_events: list[dict[str, Any]] = field(default_factory=list)
    waiting_events: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SessionLocalReorderWindow:
    stable_after: timedelta = timedelta(minutes=2)
    hold_for: timedelta = timedelta(minutes=3)

    def rebalance(self, events: list[dict[str, Any]], *, now: datetime | None = None) -> ContextReorderWindowResult:
        reference = (now or datetime.now(UTC)).astimezone(UTC)
        normalized = sorted((self._normalize_event(item) for item in events), key=lambda item: item["timestamp"])
        stable_cutoff = reference - self.hold_for
        waiting_cutoff = reference - self.stable_after

        stable: list[dict[str, Any]] = []
        waiting: list[dict[str, Any]] = []
        for event in normalized:
            timestamp = event["timestamp"]
            if timestamp <= stable_cutoff:
                stable.append(self._serialize_event(event))
            elif timestamp <= waiting_cutoff:
                waiting.append(self._serialize_event(event))
            else:
                waiting.append(self._serialize_event(event))
        return ContextReorderWindowResult(stable_events=stable, waiting_events=waiting)

    def _normalize_event(self, event: dict[str, Any]) -> dict[str, Any]:
        payload = dict(event)
        payload["timestamp"] = self._parse_timestamp(payload.get("timestamp"))
        return payload

    def _serialize_event(self, event: dict[str, Any]) -> dict[str, Any]:
        payload = dict(event)
        timestamp = payload.get("timestamp")
        if isinstance(timestamp, datetime):
            payload["timestamp"] = timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")
        return payload

    def _parse_timestamp(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value.astimezone(UTC)
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
        raise ValueError("event timestamp is required")
