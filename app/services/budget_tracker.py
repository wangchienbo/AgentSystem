"""Budget tracker for AgentSystem to monitor and control token/cost usage."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from collections import defaultdict


@dataclass
class BudgetConfig:
    """Configuration for budget tracking."""
    token_budget_per_session: int = 100000
    token_budget_per_user_per_day: int = 500000
    token_budget_per_command: int = 20000
    api_cost_per_1k_tokens: float = 0.002  # USD


@dataclass
class BudgetState:
    """State tracking for budget."""
    tokens_used: int = 0
    command_tokens_used: int = 0
    last_reset_time: float = field(default_factory=time.time)


class BudgetExceededError(ValueError):
    """Raised when budget is exceeded."""
    def __init__(self, budget_type: str, used: int, limit: int):
        self.budget_type = budget_type
        self.used = used
        self.limit = limit
        super().__init__(f"{budget_type} budget exceeded: {used}/{limit} tokens")


class BudgetTracker:
    """Tracks and enforces token/cost budgets for AgentSystem."""
    
    def __init__(self, config: BudgetConfig | None = None):
        self.config = config or BudgetConfig()
        self._session_states: dict[str, BudgetState] = defaultdict(BudgetState)
        self._user_daily_states: dict[str, BudgetState] = defaultdict(BudgetState)
        self._lock = Lock()
    
    def _reset_daily_budgets_if_needed(self, current_time: float) -> None:
        """Reset daily budgets if a new day has started (simplified: 24h window)."""
        # For simplicity, we reset if more than 24 hours have passed
        seconds_in_day = 24 * 60 * 60
        for state in list(self._user_daily_states.values()):
            if current_time - state.last_reset_time > seconds_in_day:
                state.tokens_used = 0
                state.command_tokens_used = 0
                state.last_reset_time = current_time
    
    def consume_tokens(self, session_id: str, user_id: str | None, tokens: int) -> tuple[bool, str | None]:
        """Consume tokens from budget.
        
        Returns:
            Tuple of (success, error_message_if_failed)
        """
        with self._lock:
            current_time = time.time()
            self._reset_daily_budgets_if_needed(current_time)
            
            session_state = self._session_states[session_id]
            
            # Check per-command budget
            if session_state.command_tokens_used + tokens > self.config.token_budget_per_command:
                return False, f"Command token budget exceeded: {session_state.command_tokens_used + tokens}/{self.config.token_budget_per_command}"
            
            # Check per-session budget
            if session_state.tokens_used + tokens > self.config.token_budget_per_session:
                return False, f"Session token budget exceeded: {session_state.tokens_used + tokens}/{self.config.token_budget_per_session}"
            
            # Check per-user daily budget
            if user_id:
                user_state = self._user_daily_states[user_id]
                if user_state.tokens_used + tokens > self.config.token_budget_per_user_per_day:
                    return False, f"User daily token budget exceeded: {user_state.tokens_used + tokens}/{self.config.token_budget_per_user_per_day}"
                user_state.tokens_used += tokens
            
            # Consume from session
            session_state.tokens_used += tokens
            session_state.command_tokens_used += tokens
            
            return True, None
    
    def reset_command_budget(self, session_id: str) -> None:
        """Reset command-level budget for a new command."""
        with self._lock:
            self._session_states[session_id].command_tokens_used = 0
    
    def get_session_usage(self, session_id: str) -> dict:
        """Get current token usage for a session."""
        with self._lock:
            state = self._session_states[session_id]
            return {
                "tokens_used": state.tokens_used,
                "command_tokens_used": state.command_tokens_used,
                "budget_per_session": self.config.token_budget_per_session,
                "budget_per_command": self.config.token_budget_per_command,
                "usage_percent": (state.tokens_used / self.config.token_budget_per_session) * 100 if self.config.token_budget_per_session > 0 else 0,
            }
    
    def get_user_daily_usage(self, user_id: str) -> dict:
        """Get current daily token usage for a user."""
        with self._lock:
            state = self._user_daily_states.get(user_id, BudgetState())
            return {
                "tokens_used": state.tokens_used,
                "budget_per_day": self.config.token_budget_per_user_per_day,
                "usage_percent": (state.tokens_used / self.config.token_budget_per_user_per_day) * 100 if self.config.token_budget_per_user_per_day > 0 else 0,
            }
    
    def reset_session(self, session_id: str) -> None:
        """Reset all budgets for a session."""
        with self._lock:
            if session_id in self._session_states:
                del self._session_states[session_id]
