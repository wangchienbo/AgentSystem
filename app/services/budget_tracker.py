"""Budget tracker for AgentSystem - backward compatibility module.

This module is now a thin wrapper around ResourceBudgetManager.
For new code, use app.services.resource_budget_manager directly.

ADR-001: Budget/Quota System Unification - Phase 1
"""
from __future__ import annotations

# Forward all imports to the new unified module
from app.services.resource_budget_manager import (
    ResourceType,
    ResourceConsumption,
    ResourceBudgetConfig as BudgetConfig,
    BudgetStatus,
    IResourceBudgetManager,
    ResourceBudgetManager as BudgetTracker,
)

# Keep BudgetExceededError for backward compatibility
class BudgetExceededError(ValueError):
    """Raised when budget is exceeded."""
    def __init__(self, budget_type: str, used: int, limit: int):
        self.budget_type = budget_type
        self.used = used
        self.limit = limit
        super().__init__(f"{budget_type} budget exceeded: {used}/{limit} tokens")


__all__ = [
    "BudgetConfig",
    "BudgetTracker",
    "BudgetExceededError",
    "ResourceType",
    "ResourceConsumption",
    "BudgetStatus",
    "IResourceBudgetManager",
    "ResourceBudgetManager",
]
