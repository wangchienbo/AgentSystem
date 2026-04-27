"""Observability utilities for AgentSystem - logging, metrics, and tracing."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import UTC, datetime
from typing import Any


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('agentsystem')


@dataclass
class CommandMetrics:
    """Metrics for a single command execution."""
    session_id: str
    user_id: str | None
    command_type: str
    target_app: str | None
    status: str  # success, error, blocked
    duration_ms: int
    tokens_used: int = 0
    tool_calls: int = 0
    error: str | None = None
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class ObservabilityCollector:
    """Collects and exports observability data."""
    
    def __init__(self):
        self._metrics: list[CommandMetrics] = []
        self._command_counter = 0
        self._error_counter = 0
        self._blocked_counter = 0
        self._total_duration_ms = 0
        self._total_tokens = 0
        self._total_tool_calls = 0
    
    def record_command(self, metrics: CommandMetrics) -> None:
        """Record metrics for a command execution."""
        self._metrics.append(metrics)
        self._command_counter += 1
        self._total_duration_ms += metrics.duration_ms
        self._total_tokens += metrics.tokens_used
        self._total_tool_calls += metrics.tool_calls
        
        if metrics.status == "error":
            self._error_counter += 1
        elif metrics.status == "blocked":
            self._blocked_counter += 1
        
        # Log the metrics
        logger.info(f"Command: {metrics.command_type}, Status: {metrics.status}, Duration: {metrics.duration_ms}ms, Tokens: {metrics.tokens_used}")
        if metrics.error:
            logger.error(f"Command error: {metrics.error}")
    
    def get_summary(self) -> dict:
        """Get summary statistics."""
        avg_duration = self._total_duration_ms / self._command_counter if self._command_counter > 0 else 0
        return {
            "total_commands": self._command_counter,
            "error_count": self._error_counter,
            "blocked_count": self._blocked_counter,
            "total_duration_ms": self._total_duration_ms,
            "average_duration_ms": avg_duration,
            "total_tokens": self._total_tokens,
            "total_tool_calls": self._total_tool_calls,
        }
    
    def get_metrics_export(self) -> str:
        """Export metrics in Prometheus-like format."""
        summary = self.get_summary()
        lines = [
            "# HELP agentsystem_commands_total Total number of commands executed",
            "# TYPE agentsystem_commands_total counter",
            f"agentsystem_commands_total {summary['total_commands']}",
            "",
            "# HELP agentsystem_errors_total Total number of command errors",
            "# TYPE agentsystem_errors_total counter",
            f"agentsystem_errors_total {summary['error_count']}",
            "",
            "# HELP agentsystem_blocked_total Total number of blocked commands",
            "# TYPE agentsystem_blocked_total counter",
            f"agentsystem_blocked_total {summary['blocked_count']}",
            "",
            "# HELP agentsystem_duration_ms_total Total duration of all commands in milliseconds",
            "# TYPE agentsystem_duration_ms_total counter",
            f"agentsystem_duration_ms_total {summary['total_duration_ms']}",
            "",
            "# HELP agentsystem_tokens_total Total tokens used",
            "# TYPE agentsystem_tokens_total counter",
            f"agentsystem_tokens_total {summary['total_tokens']}",
            "",
            "# HELP agentsystem_tool_calls_total Total tool calls made",
            "# TYPE agentsystem_tool_calls_total counter",
            f"agentsystem_tool_calls_total {summary['total_tool_calls']}",
        ]
        return "\n".join(lines)


# Global collector instance
collector = ObservabilityCollector()


def create_command_context(session_id: str, user_id: str | None, command_type: str, target_app: str | None = None) -> CommandContext:
    """Create a context manager for command timing and metrics."""
    return CommandContext(session_id, user_id, command_type, target_app)


class CommandContext:
    """Context manager for tracking command execution metrics."""
    
    def __init__(self, session_id: str, user_id: str | None, command_type: str, target_app: str | None = None):
        self.session_id = session_id
        self.user_id = user_id
        self.command_type = command_type
        self.target_app = target_app
        self.start_time: float | None = None
        self.tokens_used: int = 0
        self.tool_calls: int = 0
        self.error: str | None = None
        self.status: str = "success"
    
    def __enter__(self) -> CommandContext:
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = int((time.time() - self.start_time) * 1000) if self.start_time else 0
        
        if exc_type is not None:
            self.status = "error"
            self.error = str(exc_val) if exc_val else str(exc_type)
        
        metrics = CommandMetrics(
            session_id=self.session_id,
            user_id=self.user_id,
            command_type=self.command_type,
            target_app=self.target_app,
            status=self.status,
            duration_ms=duration_ms,
            tokens_used=self.tokens_used,
            tool_calls=self.tool_calls,
            error=self.error,
        )
        
        collector.record_command(metrics)
        return False  # Don't suppress exceptions
    
    def add_tokens(self, tokens: int) -> None:
        """Add token usage."""
        self.tokens_used += tokens
    
    def add_tool_call(self) -> None:
        """Increment tool call counter."""
        self.tool_calls += 1
    
    def set_error(self, error: str) -> None:
        """Set error status."""
        self.status = "error"
        self.error = error
    
    def set_blocked(self, reason: str) -> None:
        """Set blocked status."""
        self.status = "blocked"
        self.error = reason
