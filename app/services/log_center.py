"""Log Center — unified skill runtime log storage and query.

All skills write their logs here. Supports querying by trace_id,
skill_id, app_instance_id, level, and time range.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from app.models.log_center import (
    LOG_LEVEL_ORDER,
    LogLevel,
    LogCollectionConfig,
    LogQuery,
    SkillLogEntry,
)

logger = logging.getLogger(__name__)


class LogCenter:
    """Central log storage for all skill runtime logs.

    Supports:
    - Per-app collection config
    - Trace-based querying (full call chain)
    - Level filtering
    - Automatic retention cleanup
    """

    def __init__(self) -> None:
        # trace_id → [entries]
        self._by_trace: dict[str, list[SkillLogEntry]] = defaultdict(list)
        # skill_id → [entries]
        self._by_skill: dict[str, list[SkillLogEntry]] = defaultdict(list)
        # app_instance_id → [entries]
        self._by_app: dict[str, list[SkillLogEntry]] = defaultdict(list)
        # app_instance_id → config
        self._app_configs: dict[str, LogCollectionConfig] = {}
        # Total entry count
        self._total_entries = 0
        # Global max (safety limit)
        self._global_max = 100_000

    # -- Writing --------------------------------------------------------------

    def log(
        self,
        trace_id: str,
        skill_id: str,
        action: str,
        app_instance_id: str,
        user_id: str,
        level: LogLevel,
        message: str,
        inputs: dict | None = None,
        outputs: dict | None = None,
        error: str | None = None,
        duration_ms: float | None = None,
        metadata: dict | None = None,
    ) -> SkillLogEntry | None:
        """Record a log entry. Returns None if filtered by config."""
        config = self._get_config(app_instance_id)
        if not config.should_log(level):
            return None

        # Determine if we should record inputs/outputs
        record_data = config.should_record_data(level)
        if error:
            record_data = True  # always record data for errors

        entry = SkillLogEntry(
            trace_id=trace_id,
            skill_id=skill_id,
            action=action,
            app_instance_id=app_instance_id,
            user_id=user_id,
            level=level,
            message=message,
            inputs=inputs if (record_data and inputs) else None,
            outputs=outputs if (record_data and outputs) else None,
            error=error,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )

        # Store in indexes
        self._by_trace[trace_id].append(entry)
        self._by_skill[skill_id].append(entry)
        self._by_app[app_instance_id].append(entry)
        self._total_entries += 1

        # Also write to Python logger
        log_method = getattr(logger, level.lower(), logger.info)
        log_method("[%s] %s/%s: %s", trace_id, skill_id, action, message)

        # Safety: trim oldest if over limit
        if self._total_entries > self._global_max:
            self._trim_oldest()

        return entry

    def log_execution(
        self,
        trace_id: str,
        skill_id: str,
        action: str,
        app_instance_id: str,
        user_id: str,
        status: str,
        duration_ms: float,
        inputs: dict | None = None,
        outputs: dict | None = None,
        error: str | None = None,
    ) -> None:
        """Convenience: log a complete skill execution."""
        level: LogLevel = "ERROR" if status == "failed" else "INFO"
        message = f"{'failed' if status == 'failed' else 'completed'} in {duration_ms:.0f}ms"
        if error:
            message += f" — {error}"

        self.log(
            trace_id=trace_id,
            skill_id=skill_id,
            action=action,
            app_instance_id=app_instance_id,
            user_id=user_id,
            level=level,
            message=message,
            inputs=inputs,
            outputs=outputs,
            error=error,
            duration_ms=duration_ms,
        )

    def log_step_start(
        self,
        trace_id: str,
        skill_id: str,
        action: str,
        app_instance_id: str,
        user_id: str,
        step_name: str,
        inputs: dict | None = None,
    ) -> None:
        """Log the start of a step in path execution."""
        self.log(
            trace_id=trace_id,
            skill_id=skill_id,
            action=action,
            app_instance_id=app_instance_id,
            user_id=user_id,
            level="INFO",
            message=f"step_start: {step_name}",
            inputs=inputs,
        )

    # -- Querying -------------------------------------------------------------

    def query(self, q: LogQuery) -> list[SkillLogEntry]:
        """Query logs with filters."""
        entries: list[SkillLogEntry]

        if q.trace_id:
            entries = list(self._by_trace.get(q.trace_id, []))
        elif q.skill_id:
            entries = list(self._by_skill.get(q.skill_id, []))
        elif q.app_instance_id:
            entries = list(self._by_app.get(q.app_instance_id, []))
        else:
            # All entries — use most recent
            all_entries = []
            for trace_entries in self._by_trace.values():
                all_entries.extend(trace_entries)
            entries = all_entries

        # Apply filters
        if q.level:
            entries = [e for e in entries if e.level == q.level]
        if q.min_level:
            min_order = LOG_LEVEL_ORDER.get(q.min_level, 0)
            entries = [e for e in entries if LOG_LEVEL_ORDER.get(e.level, 0) >= min_order]
        if q.error_only:
            entries = [e for e in entries if e.error]
        if q.action:
            entries = [e for e in entries if e.action == q.action]
        if q.user_id:
            entries = [e for e in entries if e.user_id == q.user_id]

        # Sort by timestamp descending
        entries.sort(key=lambda e: e.timestamp, reverse=True)

        # Pagination
        return entries[q.offset: q.offset + q.limit]

    def get_trace(self, trace_id: str) -> list[SkillLogEntry]:
        """Get all log entries for a trace (full call chain)."""
        entries = self._by_trace.get(trace_id, [])
        entries.sort(key=lambda e: e.timestamp)
        return entries

    def get_trace_summary(self, trace_id: str) -> dict:
        """Summary of a trace for quick debugging."""
        entries = self.get_trace(trace_id)
        if not entries:
            return {"trace_id": trace_id, "found": False}

        skills_called = list({e.skill_id for e in entries})
        errors = [e for e in entries if e.error]
        total_duration = sum(e.duration_ms or 0 for e in entries)

        return {
            "trace_id": trace_id,
            "found": True,
            "entry_count": len(entries),
            "skills_called": skills_called,
            "error_count": len(errors),
            "total_duration_ms": total_duration,
            "first_entry": entries[0].timestamp.isoformat(),
            "last_entry": entries[-1].timestamp.isoformat(),
            "errors": [{"skill": e.skill_id, "message": e.error} for e in errors],
        }

    # -- Configuration --------------------------------------------------------

    def set_app_config(self, app_instance_id: str, config: LogCollectionConfig) -> None:
        self._app_configs[app_instance_id] = config

    def get_app_config(self, app_instance_id: str) -> LogCollectionConfig:
        return self._get_config(app_instance_id)

    def _get_config(self, app_instance_id: str) -> LogCollectionConfig:
        return self._app_configs.get(
            app_instance_id,
            LogCollectionConfig(),
        )

    # -- Maintenance ----------------------------------------------------------

    def _trim_oldest(self) -> None:
        """Remove oldest entries when over global limit."""
        all_entries = []
        for entries in self._by_trace.values():
            all_entries.extend(entries)
        all_entries.sort(key=lambda e: e.timestamp)

        trim_count = self._total_entries - self._global_max
        if trim_count <= 0:
            return

        removed = 0
        for entry in all_entries:
            if removed >= trim_count:
                break
            self._by_trace[entry.trace_id].remove(entry)
            self._by_skill[entry.skill_id].remove(entry)
            self._by_app[entry.app_instance_id].remove(entry)
            removed += 1
            self._total_entries -= 1

        logger.info("Trimmed %d old log entries", removed)

    def cleanup_expired(self) -> int:
        """Remove entries older than their retention period."""
        now = time.time()
        removed = 0

        for app_id, config in self._app_configs.items():
            cutoff = now - (config.retention_hours * 3600)
            entries = self._by_app.get(app_id, [])
            to_remove = [e for e in entries if e.timestamp.timestamp() < cutoff]

            for entry in to_remove:
                self._by_trace[entry.trace_id].remove(entry)
                self._by_skill[entry.skill_id].remove(entry)
                entries.remove(entry)
                removed += 1
                self._total_entries -= 1

        if removed:
            logger.info("Cleaned up %d expired log entries", removed)
        return removed

    def stats(self) -> dict:
        """Log center statistics."""
        return {
            "total_entries": self._total_entries,
            "traces": len(self._by_trace),
            "skills_logged": len(self._by_skill),
            "apps_logged": len(self._by_app),
            "configs": len(self._app_configs),
        }
