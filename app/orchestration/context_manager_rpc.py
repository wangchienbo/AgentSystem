"""Context Manager RPC — context compression and rule assembly.

Provides context management as an RPC service (built into the Master process).
Used by ToolCallExecutor and Skills to:
1. Compress/filter context before LLM calls
2. Load skill rules in layers (L1/L2/L3 on demand)
3. Auto-assemble common rules for all skill invocations
4. Inject user hints into running tasks

Design:
- L1 (basic description) always loaded
- L2 (detailed rules) loaded when skill is called
- L3 (full context) only for debugging
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContextBuildResult:
    """Result of building a context for an LLM call.

    Attributes:
        system_prompt: Assembled system prompt with common rules
        user_message: Processed user message
        available_tools: Filtered tool list for this call
        skill_rules: Assembled skill rules (L1+L2 by default)
        metadata: Context metadata (token count, etc.)
    """
    system_prompt: str = ""
    user_message: str = ""
    available_tools: list[dict[str, Any]] = field(default_factory=list)
    skill_rules: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ContextManagerRpc:
    """Context management RPC service.

    In single-process mode: called directly.
    In distributed mode: accessed via RPC from Master process.
    """

    def __init__(self) -> None:
        # Skill rule cache: skill_id → {L1, L2, L3}
        self._skill_rules: dict[str, dict[str, str]] = {}
        # Active hints: trace_id → list of hint texts
        self._active_hints: dict[str, list[str]] = {}
        # Common system context
        self._system_context: dict[str, Any] = {}

    def set_system_context(self, context: dict[str, Any]) -> None:
        """Set the global system context (user identity, permissions, etc.)."""
        self._system_context = context

    def register_skill_rules(
        self, skill_id: str, l1: str = "", l2: str = "", l3: str = ""
    ) -> None:
        """Register skill rules at different levels."""
        self._skill_rules[skill_id] = {"L1": l1, "L2": l2, "L3": l3}

    def get_skill_rules(
        self, skill_id: str, max_level: str = "L2"
    ) -> str:
        """Get skill rules up to a certain level.

        Args:
            skill_id: Target skill
            max_level: Maximum level to include (L1, L2, or L3)

        Returns:
            Concatenated rule text
        """
        rules = self._skill_rules.get(skill_id, {})
        levels = ["L1", "L2", "L3"]
        max_idx = levels.index(max_level) if max_level in levels else 1

        parts = []
        for level in levels[: max_idx + 1]:
            if rules.get(level):
                parts.append(f"[{level}] {rules[level]}")
        return "\n".join(parts)

    def inject_hint(self, trace_id: str, hint_text: str) -> None:
        """Inject a user hint into a running task's context."""
        if trace_id not in self._active_hints:
            self._active_hints[trace_id] = []
        self._active_hints[trace_id].append(hint_text)

    def get_hints(self, trace_id: str) -> list[str]:
        """Get all pending hints for a trace."""
        return self._active_hints.get(trace_id, [])

    def consume_hints(self, trace_id: str) -> list[str]:
        """Get and clear hints for a trace."""
        hints = self._active_hints.pop(trace_id, [])
        return hints

    def build_context(
        self,
        skill_id: str,
        user_message: str,
        available_tools: list[dict[str, Any]],
        skill_description_l1: str = "",
        max_rule_level: str = "L2",
        include_hints_for: str | None = None,
    ) -> ContextBuildResult:
        """Assemble a complete context for an LLM call.

        Auto-assembles:
        - System context
        - Skill L1 description
        - Skill rules (L1/L2/L3 on demand)
        - Available tools (already permission-filtered)
        - Active hints (if any)

        Args:
            skill_id: Target skill
            user_message: Original user message
            available_tools: Permission-filtered tool list
            skill_description_l1: L1 description of the skill
            max_rule_level: How deep to load skill rules
            include_hints_for: Include hints for this trace_id

        Returns:
            Assembled context
        """
        # Build system prompt
        system_parts = []

        if self._system_context:
            system_parts.append(f"System context: {self._system_context}")

        if skill_description_l1:
            system_parts.append(f"Skill: {skill_description_l1}")

        skill_rules = self.get_skill_rules(skill_id, max_rule_level)
        if skill_rules:
            system_parts.append(f"Rules:\n{skill_rules}")

        # Append active hints
        if include_hints_for:
            hints = self.consume_hints(include_hints_for)
            if hints:
                hint_text = "\n".join(f"💡 {h}" for h in hints)
                user_message = f"{user_message}\n\n{hint_text}"

        system_prompt = "\n---\n".join(system_parts) if system_parts else ""

        return ContextBuildResult(
            system_prompt=system_prompt,
            user_message=user_message,
            available_tools=available_tools,
            skill_rules=skill_rules,
            metadata={
                "skill_id": skill_id,
                "rule_level": max_rule_level,
                "hint_count": len(hints) if include_hints_for else 0,
            },
        )
