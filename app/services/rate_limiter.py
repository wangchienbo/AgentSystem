"""Rate limiter for AgentSystem to prevent abuse and resource exhaustion."""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    max_concurrent_queries_per_session: int = 5
    max_queries_per_user_per_minute: int = 30
    max_queries_per_session_per_minute: int = 20
    max_tool_calls_per_command: int = 10
    max_tool_calls_per_session: int = 100


@dataclass
class RateLimitState:
    """State tracking for rate limiting."""
    # Query timestamps in the last minute (for rate calculation)
    query_timestamps: list[float] = field(default_factory=list)
    # Current concurrent queries
    concurrent_queries: int = 0
    # Tool call count
    tool_call_count: int = 0


class RateLimiter:
    """Rate limiter for AgentSystem.
    
    Tracks query rates per session and user, enforcing limits to prevent abuse.
    """
    
    def __init__(self, config: RateLimitConfig | None = None):
        self.config = config or RateLimitConfig()
        self._session_states: dict[str, RateLimitState] = defaultdict(RateLimitState)
        self._lock = Lock()
    
    def _clean_old_timestamps(self, timestamps: list[float], current_time: float, window_seconds: float = 60.0) -> list[float]:
        """Remove timestamps older than the window."""
        cutoff = current_time - window_seconds
        return [ts for ts in timestamps if ts > cutoff]
    
    def try_acquire_session_slot(self, session_id: str) -> tuple[bool, str | None]:
        """Atomically validate rate limits and reserve one concurrent session slot."""
        with self._lock:
            current_time = time.time()
            state = self._session_states[session_id]

            # Clean old timestamps
            state.query_timestamps = self._clean_old_timestamps(state.query_timestamps, current_time)

            # Check concurrent queries
            if state.concurrent_queries >= self.config.max_concurrent_queries_per_session:
                return False, f"Concurrent query limit exceeded ({state.concurrent_queries}/{self.config.max_concurrent_queries_per_session})"

            # Check queries per minute
            if len(state.query_timestamps) >= self.config.max_queries_per_session_per_minute:
                return False, f"Query rate limit exceeded ({len(state.query_timestamps)}/{self.config.max_queries_per_session_per_minute} per minute)"

            state.concurrent_queries += 1
            state.query_timestamps.append(current_time)
            return True, None

    def is_session_allowed(self, session_id: str) -> tuple[bool, str | None]:
        """Check if a query is allowed for the given session.
        
        Returns:
            Tuple of (allowed, reason_if_blocked)
        """
        with self._lock:
            current_time = time.time()
            state = self._session_states[session_id]
            
            # Clean old timestamps
            state.query_timestamps = self._clean_old_timestamps(state.query_timestamps, current_time)
            
            # Check concurrent queries
            if state.concurrent_queries >= self.config.max_concurrent_queries_per_session:
                return False, f"Concurrent query limit exceeded ({state.concurrent_queries}/{self.config.max_concurrent_queries_per_session})"
            
            # Check queries per minute
            if len(state.query_timestamps) >= self.config.max_queries_per_session_per_minute:
                return False, f"Query rate limit exceeded ({len(state.query_timestamps)}/{self.config.max_queries_per_session_per_minute} per minute)"
            
            return True, None
    
    def record_query(self, session_id: str) -> None:
        """Record a query for rate tracking."""
        with self._lock:
            current_time = time.time()
            state = self._session_states[session_id]
            state.query_timestamps.append(current_time)
    
    def increment_concurrent(self, session_id: str) -> None:
        """Increment concurrent query counter."""
        with self._lock:
            self._session_states[session_id].concurrent_queries += 1
    
    def decrement_concurrent(self, session_id: str) -> None:
        """Decrement concurrent query counter."""
        with self._lock:
            state = self._session_states[session_id]
            state.concurrent_queries = max(0, state.concurrent_queries - 1)
    
    def is_tool_call_allowed(self, session_id: str, command_tool_count: int) -> tuple[bool, str | None]:
        """Check if a tool call is allowed.
        
        Returns:
            Tuple of (allowed, reason_if_blocked)
        """
        with self._lock:
            state = self._session_states[session_id]
            
            # Check per-command limit
            if command_tool_count >= self.config.max_tool_calls_per_command:
                return False, f"Tool call limit per command exceeded ({command_tool_count}/{self.config.max_tool_calls_per_command})"
            
            # Check per-session limit
            if state.tool_call_count >= self.config.max_tool_calls_per_session:
                return False, f"Tool call limit per session exceeded ({state.tool_call_count}/{self.config.max_tool_calls_per_session})"
            
            return True, None
    
    def record_tool_call(self, session_id: str) -> None:
        """Record a tool call."""
        with self._lock:
            state = self._session_states[session_id]
            state.tool_call_count += 1
    
    def reset_session(self, session_id: str) -> None:
        """Reset state for a session."""
        with self._lock:
            if session_id in self._session_states:
                del self._session_states[session_id]
