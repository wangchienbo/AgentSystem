"""Pipeline Service — workflow/pipeline management for AgentSystem.

Classifies and manages three layers of pipelines:
1. System-level: no user context, triggered by timer/events
2. User-level: has user context, no App binding
3. App-level: user + App bound

Analogous to OS process scheduling: system daemons, user processes, App sandboxed processes.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any


class PipelineType(str, Enum):
    SYSTEM = "system"       # No user, system events
    USER = "user"           # Has user, no App
    APP = "app"             # User + App bound


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PipelineError(ValueError):
    pass


class PipelineRecord:
    """A single pipeline execution record."""

    def __init__(
        self,
        pipeline_id: str,
        pipeline_type: PipelineType,
        user_id: str | None = None,
        app_id: str | None = None,
        trigger: str = "manual",
        status: PipelineStatus = PipelineStatus.PENDING,
        steps: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.pipeline_id = pipeline_id
        self.pipeline_type = pipeline_type
        self.user_id = user_id
        self.app_id = app_id
        self.trigger = trigger
        self.status = status
        self.steps = steps or []
        self.metadata = metadata or {}
        self.created_at = datetime.now(UTC).isoformat()
        self.started_at: str | None = None
        self.completed_at: str | None = None
        self.error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "pipeline_type": self.pipeline_type,
            "user_id": self.user_id,
            "app_id": self.app_id,
            "trigger": self.trigger,
            "status": self.status,
            "steps": self.steps,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PipelineRecord":
        record = cls(
            pipeline_id=data["pipeline_id"],
            pipeline_type=PipelineType(data.get("pipeline_type", "system")),
            user_id=data.get("user_id"),
            app_id=data.get("app_id"),
            trigger=data.get("trigger", "manual"),
            status=PipelineStatus(data.get("status", "pending")),
            steps=data.get("steps", []),
            metadata=data.get("metadata", {}),
        )
        record.created_at = data.get("created_at", "")
        record.started_at = data.get("started_at")
        record.completed_at = data.get("completed_at")
        record.error_message = data.get("error_message")
        return record


class PipelineService:
    """Manage pipeline execution records with type-based isolation.

    Data paths:
    - data/pipelines/system/*.json    — system pipelines
    - data/pipelines/users/{user_id}/*.json — user pipelines
    - data/pipelines/users/{user_id}/apps/{app_id}/*.json — app pipelines
    """

    def __init__(self, data_dir: str | None = None) -> None:
        base = data_dir or os.environ.get("AGENTSYSTEM_DATA_DIR", "data")
        self._base_dir = Path(base) / "pipelines"
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, PipelineRecord] = {}
        self._load_existing()

    def create_pipeline(
        self,
        pipeline_type: PipelineType,
        user_id: str | None = None,
        app_id: str | None = None,
        trigger: str = "manual",
        steps: list[dict[str, Any]] | None = None,
    ) -> PipelineRecord:
        """Create a new pipeline record.

        Args:
            pipeline_type: SYSTEM, USER, or APP
            user_id: User identifier (required for USER/APP type)
            app_id: App identifier (required for APP type)
            trigger: What triggered this pipeline
            steps: Pipeline step definitions

        Raises:
            PipelineError: If required parameters missing
        """
        # Validate type requirements
        if pipeline_type in (PipelineType.USER, PipelineType.APP) and not user_id:
            raise PipelineError(f"{pipeline_type} pipeline requires user_id")
        if pipeline_type == PipelineType.APP and not app_id:
            raise PipelineError("APP pipeline requires app_id")

        pipeline_id = f"pl_{pipeline_type.value}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"

        record = PipelineRecord(
            pipeline_id=pipeline_id,
            pipeline_type=pipeline_type,
            user_id=user_id,
            app_id=app_id,
            trigger=trigger,
            steps=steps or [],
        )

        self._records[pipeline_id] = record
        self._persist_record(record)
        return record

    def start_pipeline(self, pipeline_id: str) -> PipelineRecord:
        """Mark pipeline as running."""
        record = self._get_record(pipeline_id)
        record.status = PipelineStatus.RUNNING
        record.started_at = datetime.now(UTC).isoformat()
        self._persist_record(record)
        return record

    def complete_pipeline(self, pipeline_id: str) -> PipelineRecord:
        """Mark pipeline as completed."""
        record = self._get_record(pipeline_id)
        record.status = PipelineStatus.COMPLETED
        record.completed_at = datetime.now(UTC).isoformat()
        self._persist_record(record)
        return record

    def fail_pipeline(self, pipeline_id: str, error: str) -> PipelineRecord:
        """Mark pipeline as failed."""
        record = self._get_record(pipeline_id)
        record.status = PipelineStatus.FAILED
        record.completed_at = datetime.now(UTC).isoformat()
        record.error_message = error
        self._persist_record(record)
        return record

    def cancel_pipeline(self, pipeline_id: str) -> PipelineRecord:
        """Mark pipeline as cancelled."""
        record = self._get_record(pipeline_id)
        record.status = PipelineStatus.CANCELLED
        record.completed_at = datetime.now(UTC).isoformat()
        self._persist_record(record)
        return record

    def get_pipeline(self, pipeline_id: str) -> PipelineRecord | None:
        """Get a pipeline by ID."""
        return self._records.get(pipeline_id)

    def list_pipelines(
        self,
        pipeline_type: PipelineType | None = None,
        user_id: str | None = None,
        status: PipelineStatus | None = None,
        limit: int = 50,
    ) -> list[PipelineRecord]:
        """List pipelines with optional filters."""
        records = list(self._records.values())

        if pipeline_type:
            records = [r for r in records if r.pipeline_type == pipeline_type]
        if user_id:
            records = [r for r in records if r.user_id == user_id]
        if status:
            records = [r for r in records if r.status == status]

        # Sort by created_at descending
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[:limit]

    def get_user_pipelines(self, user_id: str) -> list[PipelineRecord]:
        """Get all pipelines for a user (USER + APP type)."""
        return [
            r for r in self._records.values()
            if r.user_id == user_id and r.pipeline_type in (PipelineType.USER, PipelineType.APP)
        ]

    def get_system_pipelines(self) -> list[PipelineRecord]:
        """Get all system-level pipelines."""
        return [
            r for r in self._records.values()
            if r.pipeline_type == PipelineType.SYSTEM
        ]

    def get_stats(self) -> dict[str, Any]:
        """Get pipeline statistics."""
        total = len(self._records)
        by_type: dict[str, int] = {}
        by_status: dict[str, int] = {}

        for r in self._records.values():
            by_type[r.pipeline_type] = by_type.get(r.pipeline_type, 0) + 1
            by_status[r.status] = by_status.get(r.status, 0) + 1

        return {
            "total": total,
            "by_type": by_type,
            "by_status": by_status,
        }

    def _get_record(self, pipeline_id: str) -> PipelineRecord:
        record = self._records.get(pipeline_id)
        if not record:
            raise PipelineError(f"Pipeline not found: {pipeline_id}")
        return record

    def _persist_record(self, record: PipelineRecord) -> None:
        """Persist pipeline record to disk."""
        path = self._get_record_path(record)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(json.dumps(record.to_dict(), indent=2, ensure_ascii=False))
        except OSError:
            pass  # Best effort

    def _get_record_path(self, record: PipelineRecord) -> Path:
        """Get the file path for a pipeline record."""
        if record.pipeline_type == PipelineType.SYSTEM:
            return self._base_dir / "system" / f"{record.pipeline_id}.json"
        elif record.pipeline_type == PipelineType.USER:
            return self._base_dir / "users" / record.user_id / f"{record.pipeline_id}.json"
        else:  # APP
            return (
                self._base_dir
                / "users" / record.user_id
                / "apps" / record.app_id
                / f"{record.pipeline_id}.json"
            )

    def _load_existing(self) -> None:
        """Load existing pipeline records from disk."""
        for path in self._base_dir.rglob("*.json"):
            try:
                data = json.loads(path.read_text())
                record = PipelineRecord.from_dict(data)
                self._records[record.pipeline_id] = record
            except Exception:
                continue
