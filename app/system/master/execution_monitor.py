"""Execution Monitor — tracks active tasks and handles user intent P0 preemption.

Key responsibility: when a new user message arrives (P0), this monitor
ensures the current waiting-for-model request yields and the new intent
is routed to the appropriate handler.

This is NOT a general-purpose task tracker — it's specifically for:
1. Tracking what task is currently active per session
2. Detecting when user sends a new message (intent change)
3. Flagging current tasks for preemption
4. Providing task context to the intent router
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ActiveTask:
    """A task currently being executed."""
    task_id: str
    session_id: str
    user_id: str
    intent: str              # What the user originally asked
    status: str = "running"  # "running" | "waiting_model" | "completed" | "preempted"
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    # If preempted, what replaced it
    preempted_by: str = ""   # task_id of the replacement


class ExecutionMonitor:
    """Monitors active tasks and enforces user intent priority."""

    def __init__(self) -> None:
        self._tasks: dict[str, ActiveTask] = {}       # task_id -> task
        self._session_tasks: dict[str, str] = {}       # session_id -> current task_id
        self._completed: list[ActiveTask] = []          # recent completed tasks

    def start_task(
        self,
        task_id: str,
        session_id: str,
        user_id: str,
        intent: str,
        metadata: dict[str, Any] | None = None,
    ) -> ActiveTask:
        """Register a new active task."""
        now = datetime.now(timezone.utc).isoformat()
        task = ActiveTask(
            task_id=task_id,
            session_id=session_id,
            user_id=user_id,
            intent=intent,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )
        self._tasks[task_id] = task
        self._session_tasks[session_id] = task_id
        return task

    def mark_waiting_model(self, task_id: str) -> None:
        """Mark a task as waiting for model response."""
        task = self._tasks.get(task_id)
        if task:
            task.status = "waiting_model"
            task.updated_at = datetime.now(timezone.utc).isoformat()

    def preempt_task(self, session_id: str, new_task_id: str) -> ActiveTask | None:
        """Preempt the current task in a session when user sends new message.

        Returns the preempted task, or None if no task was running.
        """
        current_id = self._session_tasks.get(session_id)
        if not current_id or current_id == new_task_id:
            return None

        current = self._tasks.get(current_id)
        if not current:
            return None

        # Only preempt if waiting for model (running tasks may still produce value)
        if current.status == "waiting_model":
            current.status = "preempted"
            current.preempted_by = new_task_id
            current.updated_at = datetime.now(timezone.utc).isoformat()
            logger.info("Preempted task %s with %s in session %s", current_id, new_task_id, session_id)
            return current

        return None

    def complete_task(self, task_id: str) -> None:
        """Mark a task as completed."""
        task = self._tasks.get(task_id)
        if task:
            task.status = "completed"
            task.updated_at = datetime.now(timezone.utc).isoformat()
            self._completed.append(task)
            # Keep only last 100 completed
            if len(self._completed) > 100:
                self._completed = self._completed[-100:]

    def get_active_task(self, session_id: str) -> ActiveTask | None:
        """Get the current active task for a session."""
        task_id = self._session_tasks.get(session_id)
        if task_id:
            task = self._tasks.get(task_id)
            if task and task.status in ("running", "waiting_model"):
                return task
        return None

    def list_active_tasks(self) -> list[ActiveTask]:
        """List all non-completed tasks."""
        return [
            t for t in self._tasks.values()
            if t.status in ("running", "waiting_model")
        ]

    def get_task(self, task_id: str) -> ActiveTask | None:
        """Get any task by ID."""
        return self._tasks.get(task_id)
