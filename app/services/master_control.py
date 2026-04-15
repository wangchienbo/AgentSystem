"""Master Control Plane — governance boundary for the AgentSystem.

This is the system's self-governance layer. It handles:
1. Permission approval for high-risk operations
2. Audit logging of all significant actions
3. Context governance (session boundaries, memory lifecycle)
4. Self-governance (system health, error recovery)
5. Infrastructure management (gateway, model routing)
6. High-risk operation control (user confirmation required)

Key principle: interaction layer doesn't absorb these responsibilities.
Master control is a separate boundary — not a business layer, not a service layer.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================
# Audit Log
# ============================================================

class AuditLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditCategory(str, Enum):
    PERMISSION = "permission"
    RESOURCE = "resource"
    MODEL = "model"
    ASSET = "asset"
    SYSTEM = "system"
    USER_ACTION = "user_action"
    RISK_OPERATION = "risk_operation"


@dataclass
class AuditRecord:
    """A single audit log entry."""
    record_id: str
    timestamp: str
    category: AuditCategory
    level: AuditLevel
    actor: str  # "user.xxx", "system", "app.xxx"
    action: str
    target: str
    details: dict[str, Any] = field(default_factory=dict)
    result: str = "pending"  # "pending" | "approved" | "denied" | "completed" | "failed"
    reviewer: str = ""


class AuditLogger:
    """Persistent audit logger for governance tracking."""

    def __init__(self, data_dir: str = "data") -> None:
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._records: list[AuditRecord] = []
        self._counter = 0
        self._load()

    def log(
        self,
        category: AuditCategory,
        level: AuditLevel,
        actor: str,
        action: str,
        target: str,
        details: dict[str, Any] | None = None,
        result: str = "pending",
        reviewer: str = "",
    ) -> AuditRecord:
        """Create an audit record."""
        self._counter += 1
        record = AuditRecord(
            record_id=f"AUDIT-{self._counter:06d}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            category=category,
            level=level,
            actor=actor,
            action=action,
            target=target,
            details=details or {},
            result=result,
            reviewer=reviewer,
        )
        self._records.append(record)
        self._save()
        if level in (AuditLevel.ERROR, AuditLevel.CRITICAL):
            logger.warning("Audit %s: %s → %s on %s", level.value, actor, action, target)
        return record

    def query(
        self,
        category: AuditCategory | None = None,
        actor: str | None = None,
        since: str | None = None,
        limit: int = 50,
    ) -> list[AuditRecord]:
        """Query audit records with optional filters."""
        records = self._records
        if category:
            records = [r for r in records if r.category == category]
        if actor:
            records = [r for r in records if r.actor == actor]
        if since:
            records = [r for r in records if r.timestamp >= since]
        return records[-limit:]

    def _load(self) -> None:
        path = self._data_dir / "audit_log.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._counter = data.get("counter", 0)
                for raw in data.get("records", []):
                    self._records.append(AuditRecord(**raw))
            except Exception:
                pass

    def _save(self) -> None:
        path = self._data_dir / "audit_log.json"
        data = {
            "counter": self._counter,
            "records": [
                {
                    "record_id": r.record_id,
                    "timestamp": r.timestamp,
                    "category": r.category.value,
                    "level": r.level.value,
                    "actor": r.actor,
                    "action": r.action,
                    "target": r.target,
                    "details": r.details,
                    "result": r.result,
                    "reviewer": r.reviewer,
                }
                for r in self._records[-1000:]  # keep last 1000
            ],
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================
# Risk Operation Governance
# ============================================================

RISK_OPERATIONS = {
    "asset_delete": "Delete an installed asset",
    "asset_rollback": "Rollback an asset to a previous version",
    "resource_terminate": "Force-terminate a running resource",
    "model_switch": "Switch the default model",
    "system_restart": "Restart the system",
    "permission_override": "Override a permission rule",
    "config_modify": "Modify system-level configuration",
}


class RiskGovernanceService:
    """Manages high-risk operation approval workflow.

    Before executing a risky operation:
    1. Log the intent as pending
    2. Require user/system approval
    3. Execute only after approval
    4. Log the result
    """

    def __init__(self, audit_logger: AuditLogger | None = None) -> None:
        self._audit = audit_logger or AuditLogger()
        self._pending_approvals: dict[str, AuditRecord] = {}

    def request_approval(
        self,
        operation: str,
        actor: str,
        target: str,
        reason: str = "",
    ) -> AuditRecord | None:
        """Request approval for a risky operation."""
        if operation not in RISK_OPERATIONS:
            logger.warning("Unknown risk operation: %s", operation)
            return None

        record = self._audit.log(
            category=AuditCategory.RISK_OPERATION,
            level=AuditLevel.WARNING,
            actor=actor,
            action=operation,
            target=target,
            details={"reason": reason, "description": RISK_OPERATIONS[operation]},
            result="pending",
        )
        self._pending_approvals[record.record_id] = record
        return record

    def approve(self, record_id: str, reviewer: str) -> AuditRecord | None:
        """Approve a pending operation."""
        record = self._pending_approvals.get(record_id)
        if not record:
            return None
        record.result = "approved"
        record.reviewer = reviewer
        self._audit.log(
            category=AuditCategory.PERMISSION,
            level=AuditLevel.INFO,
            actor=reviewer,
            action="approve",
            target=record_id,
            result="completed",
            reviewer=reviewer,
        )
        return record

    def deny(self, record_id: str, reviewer: str, reason: str = "") -> AuditRecord | None:
        """Deny a pending operation."""
        record = self._pending_approvals.get(record_id)
        if not record:
            return None
        record.result = "denied"
        record.reviewer = reviewer
        record.details["deny_reason"] = reason
        return record

    def get_pending(self) -> list[AuditRecord]:
        """List all pending approvals."""
        return list(self._pending_approvals.values())

    def clear_resolved(self) -> None:
        """Remove approved/denied records from pending queue."""
        self._pending_approvals = {
            rid: r for rid, r in self._pending_approvals.items()
            if r.result == "pending"
        }


# ============================================================
# Master Control Service
# ============================================================

class MasterControlService:
    """Top-level governance orchestrator.

    Coordinates audit logging, risk governance, and system self-governance.
    This is the system's control plane — not part of the interaction layer.
    """

    def __init__(
        self,
        data_dir: str = "data",
        auto_audit: bool = True,
    ) -> None:
        self._audit = AuditLogger(data_dir=data_dir)
        self._risk = RiskGovernanceService(audit_logger=self._audit)
        self._auto_audit = auto_audit

    @property
    def audit(self) -> AuditLogger:
        return self._audit

    @property
    def risk(self) -> RiskGovernanceService:
        return self._risk

    # ---- System self-governance ----

    def record_system_event(
        self,
        event_type: str,
        details: dict[str, Any],
        level: AuditLevel = AuditLevel.INFO,
    ) -> AuditRecord:
        """Record a system-level event."""
        return self._audit.log(
            category=AuditCategory.SYSTEM,
            level=level,
            actor="system",
            action=event_type,
            target="system",
            details=details,
            result="completed",
        )

    def record_model_call(
        self,
        model: str,
        prompt_length: int,
        success: bool,
        duration_ms: float = 0,
        error: str = "",
    ) -> AuditRecord:
        """Record a model API call for monitoring."""
        return self._audit.log(
            category=AuditCategory.MODEL,
            level=AuditLevel.INFO if success else AuditLevel.WARNING,
            actor="system",
            action="model_call",
            target=model,
            details={
                "prompt_length": prompt_length,
                "success": success,
                "duration_ms": duration_ms,
                "error": error,
            },
            result="completed" if success else "failed",
        )

    def record_asset_operation(
        self,
        operation: str,
        asset_id: str,
        actor: str,
        details: dict[str, Any] | None = None,
    ) -> AuditRecord:
        """Record an asset lifecycle operation."""
        return self._audit.log(
            category=AuditCategory.ASSET,
            level=AuditLevel.INFO,
            actor=actor,
            action=operation,
            target=asset_id,
            details=details or {},
            result="completed",
        )

    def record_resource_operation(
        self,
        operation: str,
        resource_id: str,
        actor: str,
        details: dict[str, Any] | None = None,
    ) -> AuditRecord:
        """Record a resource lifecycle operation."""
        return self._audit.log(
            category=AuditCategory.RESOURCE,
            level=AuditLevel.INFO,
            actor=actor,
            action=operation,
            target=resource_id,
            details=details or {},
            result="completed",
        )
