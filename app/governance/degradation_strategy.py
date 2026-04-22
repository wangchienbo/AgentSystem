"""Degradation Strategy - 降级策略
定义系统在依赖服务不可用时的降级行为
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable
from datetime import UTC, datetime

class DegradationMode(Enum):
    """Degradation modes."""
    FULL = "full"  # All features available
    DEGRADED_LLM = "degraded_llm"  # LLM unavailable
    DEGRADED_RUNTIME = "degraded_runtime"  # Runtime unavailable
    DEGRADED_PERSISTENCE = "degraded_persistence"  # Persistence unavailable
    OFFLINE = "offline"  # Multiple services unavailable

@dataclass
class DegradationStrategy:
    """
    Define and execute degradation strategies for different failure scenarios.
    """
    
    def __init__(self) -> None:
        self._mode = DegradationMode.FULL
        self._failure_counts: dict[str, int] = {}
        self._last_failure: dict[str, datetime] = {}
        self._strategies: dict[str, Callable] = {}
        self._register_default_strategies()
    
    def _register_default_strategies(self) -> None:
        """Register default degradation strategies."""
        self._strategies = {
            "llm_unavailable": self._handle_llm_unavailable,
            "runtime_unavailable": self._handle_runtime_unavailable,
            "persistence_unavailable": self._handle_persistence_unavailable,
            "bridge_unavailable": self._handle_bridge_unavailable,
        }
    
    def get_mode(self) -> DegradationMode:
        """Get current degradation mode."""
        return self._mode
    
    def set_mode(self, mode: DegradationMode) -> None:
        """Set degradation mode."""
        self._mode = mode
    
    def handle_failure(self, component: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Handle a component failure.
        
        Returns appropriate fallback response.
        
        Args:
            component: Failed component name
            context: Additional context about the failure
            
        Returns:
            Fallback response dict
        """
        self._failure_counts[component] = self._failure_counts.get(component, 0) + 1
        self._last_failure[component] = datetime.now(UTC)
        
        # Update mode based on failure
        if component == "llm":
            self._mode = DegradationMode.DEGRADED_LLM
        elif component == "runtime":
            self._mode = DegradationMode.DEGRADED_RUNTIME
        elif component == "persistence":
            self._mode = DegradationMode.DEGRADED_PERSISTENCE
        
        strategy = self._strategies.get(f"{component}_unavailable")
        if strategy:
            return strategy(context or {})
        
        return {
            "status": "degraded",
            "message": f"System degraded due to {component} failure",
        }
    
    def _handle_llm_unavailable(self, context: dict[str, Any]) -> dict[str, Any]:
        """Handle LLM unavailability."""
        return {
            "status": "degraded",
            "mode": "llm_unavailable",
            "message": "LLM service is currently unavailable. Using fallback responses.",
            "fallback_enabled": True,
            "features_available": ["app_management", "tool_execution", "basic_queries"],
            "features_unavailable": ["natural_language_understanding", "complex_reasoning"],
        }
    
    def _handle_runtime_unavailable(self, context: dict[str, Any]) -> dict[str, Any]:
        """Handle runtime unavailability."""
        return {
            "status": "degraded",
            "mode": "runtime_unavailable",
            "message": "Runtime service is currently unavailable. App execution paused.",
            "fallback_enabled": False,
            "features_available": ["app_management", "configuration"],
            "features_unavailable": ["app_execution", "real_time_operations"],
        }
    
    def _handle_persistence_unavailable(self, context: dict[str, Any]) -> dict[str, Any]:
        """Handle persistence unavailability."""
        return {
            "status": "degraded",
            "mode": "persistence_unavailable",
            "message": "Persistence service is currently unavailable. Changes may not be saved.",
            "fallback_enabled": True,
            "warning": "Data may be lost on restart",
            "features_available": ["temporary_operations"],
            "features_unavailable": ["data_persistence", "state_recovery"],
        }
    
    def _handle_bridge_unavailable(self, context: dict[str, Any]) -> dict[str, Any]:
        """Handle bridge unavailability."""
        return {
            "status": "degraded",
            "mode": "bridge_unavailable",
            "message": "Bridge service is currently unavailable. External integrations paused.",
            "fallback_enabled": False,
            "features_available": ["local_operations"],
            "features_unavailable": ["external_integrations", "remote_execution"],
        }
    
    def get_status(self) -> dict[str, Any]:
        """Get current degradation status."""
        return {
            "mode": self._mode.value,
            "failure_counts": self._failure_counts.copy(),
            "last_failure": {k: v.isoformat() for k, v in self._last_failure.items()},
            "available_features": self._get_available_features(),
        }
    
    def _get_available_features(self) -> list[str]:
        """Get list of available features based on current mode."""
        if self._mode == DegradationMode.FULL:
            return ["all"]
        elif self._mode == DegradationMode.DEGRADED_LLM:
            return ["app_management", "tool_execution", "basic_queries"]
        elif self._mode == DegradationMode.DEGRADED_RUNTIME:
            return ["app_management", "configuration"]
        elif self._mode == DegradationMode.DEGRADED_PERSISTENCE:
            return ["temporary_operations"]
        elif self._mode == DegradationMode.OFFLINE:
            return []
        return ["unknown"]
    
    def is_feature_available(self, feature: str) -> bool:
        """Check if a specific feature is available."""
        available = self._get_available_features()
        return "all" in available or feature in available
