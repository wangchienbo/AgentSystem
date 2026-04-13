"""Log center model — skill runtime log entries and collection config."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Log levels numeric ordering
LOG_LEVEL_ORDER: dict[LogLevel, int] = {
    "DEBUG": 0,
    "INFO": 1,
    "WARNING": 2,
    "ERROR": 3,
    "CRITICAL": 4,
}


class SkillLogEntry(BaseModel):
    """Single skill runtime log entry."""

    trace_id: str = Field(..., min_length=1, description="全链路追踪 ID")
    skill_id: str = Field(..., min_length=1)
    action: str = Field(default="execute")
    app_instance_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)

    level: LogLevel = "INFO"
    message: str = Field(..., min_length=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Optional details (controlled by collection config)
    inputs: dict[str, Any] | None = Field(default=None)
    outputs: dict[str, Any] | None = Field(default=None)
    error: str | None = None
    duration_ms: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_display(self) -> str:
        """Human-readable one-line display."""
        ts = self.timestamp.strftime("%H:%M:%S.%f")[:-3]
        level_tag = f"[{self.level:>8}]"
        return f"{ts} {level_tag} {self.skill_id}/{self.action}: {self.message}"


class LogCollectionConfig(BaseModel):
    """Configures what gets logged for a skill or app."""

    level: LogLevel = "INFO"
    record_inputs: bool = False
    record_outputs: bool = False
    max_entries: int = 10000
    retention_hours: int = 24

    def should_log(self, entry_level: LogLevel) -> bool:
        """Check if an entry at given level should be recorded."""
        return LOG_LEVEL_ORDER.get(entry_level, 0) >= LOG_LEVEL_ORDER.get(self.level, 0)

    def should_record_data(self, entry_level: LogLevel) -> bool:
        """Check if inputs/outputs should be recorded for this level."""
        if not self.should_log(entry_level):
            return False
        if entry_level in ("ERROR", "CRITICAL"):
            return True  # always record data for errors
        return self.record_inputs or self.record_outputs


class LogQuery(BaseModel):
    """Query parameters for searching logs."""

    trace_id: str | None = None
    skill_id: str | None = None
    app_instance_id: str | None = None
    user_id: str | None = None
    level: LogLevel | None = None
    min_level: LogLevel | None = None
    action: str | None = None
    error_only: bool = False
    limit: int = 100
    offset: int = 0
