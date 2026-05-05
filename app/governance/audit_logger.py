"""Audit Logger - 审计日志框架
记录关键操作的审计日志（谁、何时、做了什么）
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from dataclasses import dataclass, field

from app.services.context_storage_paths import DEFAULT_AUDIT_LOG_DIR

AuditAction = Literal[
    "create_app",
    "modify_app",
    "delete_app",
    "start_app",
    "stop_app",
    "grant_permission",
    "revoke_permission",
    "execute_tool",
    "llm_call",
]

@dataclass
class AuditEntry:
    """Single audit log entry."""
    timestamp: str
    action: AuditAction
    user_id: str
    target_id: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    result: Literal["success", "failure", "denied"] = "success"
    error_message: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            "user_id": self.user_id,
            "target_id": self.target_id,
            "details": self.details,
            "result": self.result,
            "error_message": self.error_message,
        }

class AuditLogger:
    """Audit logger for governance compliance."""
    
    def __init__(self, log_dir: str | Path = DEFAULT_AUDIT_LOG_DIR) -> None:
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._current_date = datetime.now(UTC).strftime("%Y-%m-%d")
        self._log_file = self._log_dir / f"{self._current_date}.jsonl"
    
    def log(
        self,
        action: AuditAction,
        user_id: str,
        target_id: str = "",
        details: dict[str, Any] | None = None,
        result: Literal["success", "failure", "denied"] = "success",
        error_message: str = "",
    ) -> AuditEntry:
        """Log an audit entry.
        
        Args:
            action: Type of action being performed
            user_id: ID of the user performing the action
            target_id: ID of the target resource (app, skill, etc.)
            details: Additional context about the action
            result: Outcome of the action
            error_message: Error message if result is failure or denied
            
        Returns:
            AuditEntry that was logged
        """
        entry = AuditEntry(
            timestamp=datetime.now(UTC).isoformat(),
            action=action,
            user_id=user_id,
            target_id=target_id,
            details=details or {},
            result=result,
            error_message=error_message,
        )
        self._write_entry(entry)
        return entry
    
    def _write_entry(self, entry: AuditEntry) -> None:
        """Write entry to log file."""
        # Check if date has changed and rotate log if needed
        current_date = datetime.now(UTC).strftime("%Y-%m-%d")
        if current_date != self._current_date:
            self._current_date = current_date
            self._log_file = self._log_dir / f"{current_date}.jsonl"
        
        with open(self._log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")
    
    def get_entries(
        self,
        date: str | None = None,
        action: AuditAction | None = None,
        user_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Retrieve audit entries with optional filters.
        
        Args:
            date: Date string (YYYY-MM-DD), defaults to today
            action: Filter by action type
            user_id: Filter by user ID
            limit: Maximum number of entries to return
            
        Returns:
            List of AuditEntry objects
        """
        if date is None:
            date = self._current_date
        
        file_path = self._log_dir / f"{date}.jsonl"
        if not file_path.exists():
            return []
        
        entries = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    # Apply filters
                    if action and data["action"] != action:
                        continue
                    if user_id and data["user_id"] != user_id:
                        continue
                    
                    entries.append(AuditEntry(**data))
                    if len(entries) >= limit:
                        break
                except (json.JSONDecodeError, KeyError):
                    continue
        
        return entries
