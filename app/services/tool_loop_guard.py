"""Tool Loop Guard for AgentSystem.

Detects and prevents infinite or excessive tool call loops.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolLoopConfig:
    """Configuration for tool loop detection."""
    # Maximum tool calls allowed per command execution
    max_tool_calls_per_command: int = 10
    # Maximum consecutive tool calls without user interaction
    max_consecutive_tool_calls: int = 20
    # Time window for detecting rapid tool calls (seconds)
    rapid_call_window_seconds: float = 5.0
    # Maximum calls within the rapid window
    max_rapid_calls: int = 15


@dataclass
class ToolCallRecord:
    """Record of a single tool call."""
    tool_name: str
    arguments: dict[str, Any]
    timestamp: float


class ToolLoopGuard:
    """Detects and prevents tool call loops.
    
    Tracks tool call patterns and blocks execution when loop-like
    behavior is detected.
    """
    
    def __init__(self, config: ToolLoopConfig | None = None):
        self.config = config or ToolLoopConfig()
        self._call_history: list[ToolCallRecord] = []
        self._current_command_calls: int = 0
    
    def reset_command(self) -> None:
        """Reset counters for a new command."""
        self._current_command_calls = 0
    
    def record_call(self, tool_name: str, arguments: dict[str, Any], timestamp: float) -> None:
        """Record a tool call for loop detection."""
        record = ToolCallRecord(
            tool_name=tool_name,
            arguments=arguments,
            timestamp=timestamp
        )
        self._call_history.append(record)
        self._current_command_calls += 1
        
        # Keep only recent history (within rapid call window)
        cutoff = timestamp - self.config.rapid_call_window_seconds
        self._call_history = [
            r for r in self._call_history if r.timestamp > cutoff
        ]
    
    def check_allowed(self, tool_name: str, arguments: dict[str, Any], timestamp: float) -> tuple[bool, str | None]:
        """Check if a tool call is allowed.
        
        Returns:
            Tuple of (allowed, reason_if_blocked)
        """
        # Check per-command limit
        if self._current_command_calls >= self.config.max_tool_calls_per_command:
            return False, f"Tool call limit per command exceeded ({self._current_command_calls}/{self.config.max_tool_calls_per_command})"
        
        # Check rapid call limit
        recent_calls = [
            r for r in self._call_history
            if r.timestamp > timestamp - self.config.rapid_call_window_seconds
        ]
        if len(recent_calls) >= self.config.max_rapid_calls:
            return False, f"Rapid tool call limit exceeded ({len(recent_calls)}/{self.config.max_rapid_calls} in {self.config.rapid_call_window_seconds}s)"
        
        # Check for repeating patterns (simple loop detection)
        if self._detect_repeating_pattern(tool_name, arguments):
            return False, "Repeating tool call pattern detected (possible infinite loop)"
        
        return True, None
    
    def _detect_repeating_pattern(self, tool_name: str, arguments: dict[str, Any], pattern_length: int = 3) -> bool:
        """Detect if the current call matches a repeating pattern.
        
        Looks for the last N calls being identical to detect simple loops.
        """
        if len(self._call_history) < pattern_length:
            return False
        
        # Check if the last N calls are all the same
        recent = self._call_history[-pattern_length:]
        if len(recent) < pattern_length:
            return False
        
        # Check if all recent calls are identical
        first = recent[0]
        for record in recent[1:]:
            if record.tool_name != first.tool_name or record.arguments != first.arguments:
                return False
        
        # Check if current call matches the pattern
        return (tool_name == first.tool_name and arguments == first.arguments)
    
    def get_stats(self) -> dict:
        """Get current statistics."""
        return {
            "total_calls": len(self._call_history),
            "command_calls": self._current_command_calls,
            "unique_tools": len(set(r.tool_name for r in self._call_history)),
        }
