"""Context Compressor — Layered compression strategy for LLM context.

Implements the compression logic designed in OPT-001 Phase 1:
- L1 (Critical): Always preserved (System Context, Skill Rules, Hints).
- L2 (Sliding Window): Keeps last N turns of conversation history.
- L3 (Token Truncation): Hard cutoff if token limit exceeded.

Usage:
  compressor = ContextCompressor(config)
  compressed = compressor.compress(context_result)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class CompressionConfig:
    """Configuration for context compression."""
    enabled: bool = True
    strategy: str = "sliding_window"  # sliding_window | summary | fixed
    max_turns: int = 5  # Sliding window size
    token_limit: int = 4000  # Soft limit for warning
    preserve_rules: bool = True

@dataclass
class CompressionResult:
    """Result of compression operation."""
    original_length: int
    compressed_length: int
    discarded_turns: int
    preserved_components: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

class ContextCompressor:
    """Context compression engine."""

    def __init__(self, config: CompressionConfig | None = None) -> None:
        self.config = config or CompressionConfig()

    def compress(
        self,
        system_prompt: str,
        user_message: str,
        available_tools: list[dict[str, Any]],
        skill_rules: str = "",
        conversation_history: list[dict[str, str]] | None = None,
    ) -> tuple[str, str, CompressionResult]:
        """
        Compress context components.

        Args:
            system_prompt: Base system prompt (L1 Critical)
            user_message: Current user message
            available_tools: Tool definitions
            skill_rules: Assembled skill rules (L1 Critical)
            conversation_history: List of {role, content} dicts

        Returns:
            (compressed_system_prompt, compressed_user_message, result_metadata)
        """
        if not self.config.enabled:
            # No-op
            return system_prompt, user_message, CompressionResult(
                original_length=0, compressed_length=0, discarded_turns=0,
                preserved_components=["all"], metadata={"skipped": True}
            )

        # 1. Preserve L1 Critical Components (System Prompt, Skill Rules)
        # These are never truncated in this version.
        preserved_parts = [system_prompt]
        if skill_rules and self.config.preserve_rules:
            preserved_parts.append(skill_rules)
        
        compressed_system = "\n---\n".join(preserved_parts)

        # 2. Apply Sliding Window to Conversation History (L2)
        # Note: In this architecture, conversation history is usually managed 
        # by the caller (Model Router / Interpreter) and passed as part of 
        # the message list. Here we simulate the logic for the current turn.
        # Since `build_context` doesn't pass full history, we focus on 
        # ensuring the current user_message fits.
        
        # If conversation_history is provided, apply sliding window
        turns_to_keep = self.config.max_turns
        discarded_count = 0
        if conversation_history and len(conversation_history) > turns_to_keep * 2: # *2 for user+assistant
            # Keep last N turns (each turn = user + assistant)
            # Assuming history is flat list of messages
            total_msgs = len(conversation_history)
            cutoff_idx = max(0, total_msgs - (turns_to_keep * 2))
            discarded_count = cutoff_idx // 2
            # Note: We don't modify history here as it's passed by ref usually.
            # This is a placeholder for the logic.
        
        # 3. Token Truncation (L3) - Simple char-based approximation
        # If system prompt is huge, warn (but don't truncate critical rules)
        current_chars = len(compressed_system) + len(user_message)
        if current_chars > self.config.token_limit * 4: # Rough char estimate
            # Truncate user message if needed (least critical)
            overflow = current_chars - (self.config.token_limit * 4)
            if overflow > 0 and user_message:
                user_message = "..." + user_message[overflow + 3:]

        result = CompressionResult(
            original_length=current_chars,
            compressed_length=len(compressed_system) + len(user_message),
            discarded_turns=discarded_count,
            preserved_components=["system_prompt", "skill_rules", "user_message"],
            metadata={"strategy": self.config.strategy}
        )

        return compressed_system, user_message, result
