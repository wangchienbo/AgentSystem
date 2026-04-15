"""Intent Router — routes user intents to appropriate handlers.

Responsibilities:
1. Classify incoming user messages (simple vs. complex, which skill/domain)
2. Route to the right execution path
3. Enforce P0 priority: new user message preempts waiting-for-model tasks
4. Feed complete context to LLM when LLM is actually needed

Key principle: handle simple things directly, only use LLM when necessary.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from app.services.execution_monitor import ExecutionMonitor
from app.services.command_queue import CommandQueue, Priority

logger = logging.getLogger(__name__)


@dataclass
class UserIntent:
    """Parsed user intent from a message."""
    session_id: str
    user_id: str
    message: str
    intent_type: str = "unknown"  # "simple" | "skill_call" | "app_interaction" | "system_command" | "question"
    target: str | None = None     # skill_id, app_id, or None
    parameters: dict[str, Any] = field(default_factory=dict)
    task_id: str = ""
    requires_llm: bool = True


class IntentRouter:
    """Routes user intents to execution paths.

    Classification flow:
    1. Check if it's a simple command (status, help, config query) → handle directly
    2. Check if it references a known skill/app → route to that skill/app
    3. Check if it's a system command → route to master control
    4. Otherwise → send to LLM with full asset/resource context
    """

    def __init__(
        self,
        execution_monitor: ExecutionMonitor | None = None,
        command_queue: CommandQueue | None = None,
    ) -> None:
        self._execution_monitor = execution_monitor or ExecutionMonitor()
        self._command_queue = command_queue or CommandQueue()
        self._simple_handlers: dict[str, Callable] = {}
        self._skill_handlers: dict[str, Callable] = {}

    def register_simple_handler(self, command: str, handler: Callable) -> None:
        """Register a handler for simple commands (no LLM needed)."""
        self._simple_handlers[command.lower()] = handler

    def register_skill_handler(self, skill_id: str, handler: Callable) -> None:
        """Register a handler for a specific skill."""
        self._skill_handlers[skill_id] = handler

    async def route(
        self,
        session_id: str,
        user_id: str,
        message: str,
    ) -> dict[str, Any]:
        """Route a user message to the appropriate handler.

        This is the primary entry point for user interaction.
        New messages are P0 — they preempt current waiting-for-model tasks.
        """
        # Step 1: Parse intent
        intent = self._parse_intent(session_id, user_id, message)
        intent.task_id = f"task-{session_id}-{len(message):04d}"

        # Step 2: Check for P0 preemption
        preempted = self._execution_monitor.preempt_task(session_id, intent.task_id)
        if preempted:
            logger.info(
                "P0 preemption in session %s: %s → %s",
                session_id,
                preempted.intent,
                intent.message[:50],
            )

        # Step 3: Register active task
        self._execution_monitor.start_task(
            task_id=intent.task_id,
            session_id=session_id,
            user_id=user_id,
            intent=intent.message,
        )

        # Step 4: Route to handler
        if intent.intent_type == "simple" and intent.target:
            return await self._handle_simple(intent)
        elif intent.intent_type == "skill_call" and intent.target:
            return await self._handle_skill(intent)
        elif intent.intent_type == "system_command":
            return await self._handle_system(intent)
        else:
            # Needs LLM — queue with P0 priority
            return await self._handle_with_llm(intent)

    async def _handle_simple(self, intent: UserIntent) -> dict[str, Any]:
        """Handle a simple command directly (no LLM)."""
        handler = self._simple_handlers.get(intent.target, "")
        if handler:
            result = await handler(**intent.parameters) if intent.parameters else await handler()
            self._execution_monitor.complete_task(intent.task_id)
            return {"status": "completed", "result": result, "used_llm": False}
        return {"status": "unknown_command", "used_llm": False}

    async def _handle_skill(self, intent: UserIntent) -> dict[str, Any]:
        """Route to a specific skill handler."""
        handler = self._skill_handlers.get(intent.target)
        if handler:
            result = await handler(**intent.parameters) if intent.parameters else await handler()
            self._execution_monitor.complete_task(intent.task_id)
            return {"status": "completed", "result": result, "used_llm": False}
        return {"status": "skill_not_found", "skill_id": intent.target, "used_llm": False}

    async def _handle_system(self, intent: UserIntent) -> dict[str, Any]:
        """Handle system-level command."""
        self._execution_monitor.complete_task(intent.task_id)
        return {"status": "system_command_queued", "used_llm": False}

    async def _handle_with_llm(self, intent: UserIntent) -> dict[str, Any]:
        """Queue the intent for LLM processing with full context."""
        self._execution_monitor.mark_waiting_model(intent.task_id)
        # The actual LLM call is handled by the higher-level orchestrator
        return {
            "status": "queued_for_llm",
            "task_id": intent.task_id,
            "used_llm": True,
        }

    def _parse_intent(
        self,
        session_id: str,
        user_id: str,
        message: str,
    ) -> UserIntent:
        """Parse user message into a structured intent.

        This is a lightweight local classifier — no LLM calls here.
        For more sophisticated classification, use a cheap model.
        """
        text = message.strip().lower()

        # Simple commands
        for cmd in self._simple_handlers:
            if text == cmd or text.startswith(f"{cmd} "):
                return UserIntent(
                    session_id=session_id,
                    user_id=user_id,
                    message=message,
                    intent_type="simple",
                    target=cmd,
                )

        # Skill calls: check if message starts with a known skill name
        for skill_id in self._skill_handlers:
            if skill_id in text:
                return UserIntent(
                    session_id=session_id,
                    user_id=user_id,
                    message=message,
                    intent_type="skill_call",
                    target=skill_id,
                )

        # System commands
        if text.startswith("/"):
            return UserIntent(
                session_id=session_id,
                user_id=user_id,
                message=message,
                intent_type="system_command",
            )

        # Default: needs LLM
        return UserIntent(
            session_id=session_id,
            user_id=user_id,
            message=message,
            intent_type="unknown",
            requires_llm=True,
        )
