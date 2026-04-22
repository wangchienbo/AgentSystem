"""Resource Budget Manager - Resource layer for token/compute budget tracking.

This is the foundation layer for all resource budget management.
The governance layer (CostQuotaManager) consumes resource metrics from this layer.

ADR-001: Budget/Quota System Unification - Phase 1
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from threading import Lock
from typing import Any


class ResourceType(Enum):
    """Types of resources that can be budgeted."""
    TOKENS = auto()
    COMPUTE = auto()  # CPU/memory
    STORAGE = auto()
    API_CALLS = auto()


@dataclass
class ResourceConsumption:
    """A single resource consumption record."""
    resource_type: ResourceType
    amount: float
    unit: str  # "tokens", "seconds", "bytes", "calls"
    timestamp: float = field(default_factory=time.time)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResourceBudgetConfig:
    """Configuration for resource budget tracking."""
    # Token budgets
    token_budget_per_session: int = 100000
    token_budget_per_user_per_day: int = 500000
    token_budget_per_command: int = 20000
    # Future: compute budgets
    compute_budget_per_session_ms: int = 60000  # 1 minute
    # Future: storage budgets
    storage_budget_per_session_mb: int = 100


@dataclass
class BudgetStatus:
    """Current status of a budget."""
    resource_type: ResourceType
    used: float
    limit: float
    remaining: float
    unit: str
    reset_time: float | None = None


class IResourceBudgetManager(ABC):
    """Interface for resource budget management.
    
    Implementations track resource consumption and enforce limits.
    The governance layer calls these methods to check resource availability.
    """
    
    @abstractmethod
    def check_and_consume(
        self,
        resource_type: ResourceType,
        session_id: str,
        user_id: str | None,
        amount: float,
        unit: str,
        context: dict[str, Any] | None = None,
    ) -> tuple[bool, str | None]:
        """Check if resource is available and consume if allowed.
        
        Returns:
            (success, error_message_if_blocked)
        """
        pass
    
    @abstractmethod
    def get_resource_status(
        self,
        resource_type: ResourceType,
        session_id: str,
        user_id: str | None = None,
    ) -> BudgetStatus:
        """Get current budget status for a resource type."""
        pass
    
    @abstractmethod
    def get_all_status(
        self,
        session_id: str,
        user_id: str | None = None,
    ) -> dict[ResourceType, BudgetStatus]:
        """Get budget status for all resource types."""
        pass
    
    @abstractmethod
    def reset_command_budget(self, session_id: str) -> None:
        """Reset command-level budget counters."""
        pass
    
    @abstractmethod
    def get_consumption_history(
        self,
        session_id: str,
        since: float | None = None,
    ) -> list[ResourceConsumption]:
        """Get consumption history for a session."""
        pass


class ResourceBudgetManager(IResourceBudgetManager):
    """Implementation of resource budget management.
    
    Tracks token, compute, and storage consumption per session and user.
    Provides unified interface for the governance layer.
    
    Backward compatible with existing BudgetTracker behavior.
    """
    
    def __init__(self, config: ResourceBudgetConfig | None = None):
        self.config = config or ResourceBudgetConfig()
        self._lock = Lock()
        
        # Session-level state
        self._session_tokens: dict[str, float] = {}
        self._session_command_tokens: dict[str, float] = {}
        self._session_compute_ms: dict[str, float] = {}
        
        # User-level state (daily)
        self._user_daily_tokens: dict[str, float] = {}
        self._user_last_reset: dict[str, float] = {}
        
        # Consumption history
        self._consumption_history: dict[str, list[ResourceConsumption]] = {}
    
    def _check_daily_reset(self, user_id: str, current_time: float) -> None:
        """Reset daily budgets if needed."""
        if user_id not in self._user_last_reset:
            self._user_last_reset[user_id] = current_time
            return
        
        seconds_in_day = 24 * 60 * 60
        if current_time - self._user_last_reset[user_id] > seconds_in_day:
            self._user_daily_tokens[user_id] = 0
            self._user_last_reset[user_id] = current_time
    
    def check_and_consume(
        self,
        resource_type: ResourceType,
        session_id: str,
        user_id: str | None,
        amount: float,
        unit: str,
        context: dict[str, Any] | None = None,
    ) -> tuple[bool, str | None]:
        """Check and consume resource."""
        with self._lock:
            current_time = time.time()
            
            if user_id:
                self._check_daily_reset(user_id, current_time)
            
            # Token budget handling
            if resource_type == ResourceType.TOKENS:
                return self._check_and_consume_tokens(
                    session_id, user_id, int(amount), current_time, context
                )
            
            # Future: compute budget handling
            if resource_type == ResourceType.COMPUTE:
                return self._check_and_consume_compute(
                    session_id, amount, current_time, context
                )
            
            # Record consumption
            consumption = ResourceConsumption(
                resource_type=resource_type,
                amount=amount,
                unit=unit,
                timestamp=current_time,
                context=context or {},
            )
            if session_id not in self._consumption_history:
                self._consumption_history[session_id] = []
            self._consumption_history[session_id].append(consumption)
            
            return True, None
    
    def _check_and_consume_tokens(
        self,
        session_id: str,
        user_id: str | None,
        tokens: int,
        current_time: float,
        context: dict[str, Any] | None,
    ) -> tuple[bool, str | None]:
        """Check and consume token budget."""
        # Initialize session state
        if session_id not in self._session_tokens:
            self._session_tokens[session_id] = 0
            self._session_command_tokens[session_id] = 0
        
        command_used = self._session_command_tokens[session_id]
        session_used = self._session_tokens[session_id]
        
        # Check per-command limit
        if command_used + tokens > self.config.token_budget_per_command:
            return False, f"Command token budget exceeded: {command_used + tokens}/{self.config.token_budget_per_command}"
        
        # Check per-session limit
        if session_used + tokens > self.config.token_budget_per_session:
            return False, f"Session token budget exceeded: {session_used + tokens}/{self.config.token_budget_per_session}"
        
        # Check per-user daily limit
        if user_id:
            if user_id not in self._user_daily_tokens:
                self._user_daily_tokens[user_id] = 0
            user_used = self._user_daily_tokens[user_id]
            if user_used + tokens > self.config.token_budget_per_user_per_day:
                return False, f"User daily token budget exceeded: {user_used + tokens}/{self.config.token_budget_per_user_per_day}"
            self._user_daily_tokens[user_id] = user_used + tokens
        
        # Consume tokens
        self._session_tokens[session_id] = session_used + tokens
        self._session_command_tokens[session_id] = command_used + tokens
        
        # Record consumption
        consumption = ResourceConsumption(
            resource_type=ResourceType.TOKENS,
            amount=tokens,
            unit="tokens",
            timestamp=current_time,
            context=context or {},
        )
        if session_id not in self._consumption_history:
            self._consumption_history[session_id] = []
        self._consumption_history[session_id].append(consumption)
        
        return True, None
    
    def _check_and_consume_compute(
        self,
        session_id: str,
        amount: float,
        current_time: float,
        context: dict[str, Any] | None,
    ) -> tuple[bool, str | None]:
        """Check and consume compute budget (placeholder for future)."""
        # TODO: Implement compute budget tracking
        return True, None
    
    def get_resource_status(
        self,
        resource_type: ResourceType,
        session_id: str,
        user_id: str | None = None,
    ) -> BudgetStatus:
        """Get current budget status."""
        with self._lock:
            if resource_type == ResourceType.TOKENS:
                used = self._session_tokens.get(session_id, 0)
                limit = self.config.token_budget_per_session
                return BudgetStatus(
                    resource_type=ResourceType.TOKENS,
                    used=used,
                    limit=limit,
                    remaining=limit - used,
                    unit="tokens",
                )
            
            # Future: other resource types
            return BudgetStatus(
                resource_type=resource_type,
                used=0,
                limit=float('inf'),
                remaining=float('inf'),
                unit="unknown",
            )
    
    def get_all_status(
        self,
        session_id: str,
        user_id: str | None = None,
    ) -> dict[ResourceType, BudgetStatus]:
        """Get status for all resource types."""
        return {
            ResourceType.TOKENS: self.get_resource_status(ResourceType.TOKENS, session_id, user_id),
            # Future: add compute, storage, etc.
        }
    
    def reset_command_budget(self, session_id: str) -> None:
        """Reset command-level budget."""
        with self._lock:
            self._session_command_tokens[session_id] = 0
    
    def get_consumption_history(
        self,
        session_id: str,
        since: float | None = None,
    ) -> list[ResourceConsumption]:
        """Get consumption history."""
        with self._lock:
            history = self._consumption_history.get(session_id, [])
            if since is not None:
                return [c for c in history if c.timestamp >= since]
            return list(history)
    
    # Backward compatibility with BudgetTracker
    def consume_tokens(
        self,
        session_id: str,
        user_id: str | None,
        tokens: int,
    ) -> tuple[bool, str | None]:
        """Backward compatible method."""
        return self.check_and_consume(
            ResourceType.TOKENS,
            session_id,
            user_id,
            tokens,
            "tokens",
        )
    
    def get_session_usage(self, session_id: str) -> dict:
        """Backward compatible method."""
        status = self.get_resource_status(ResourceType.TOKENS, session_id)
        return {
            "tokens_used": status.used,
            "command_tokens_used": self._session_command_tokens.get(session_id, 0),
            "budget_per_session": status.limit,
            "budget_per_command": self.config.token_budget_per_command,
            "usage_percent": (status.used / status.limit) * 100 if status.limit > 0 else 0,
        }
    
    def get_user_daily_usage(self, user_id: str) -> dict:
        """Backward compatible method."""
        used = self._user_daily_tokens.get(user_id, 0)
        limit = self.config.token_budget_per_user_per_day
        return {
            "tokens_used": used,
            "budget_per_day": limit,
            "usage_percent": (used / limit) * 100 if limit > 0 else 0,
        }


# Backward compatible alias
BudgetTracker = ResourceBudgetManager
BudgetConfig = ResourceBudgetConfig
