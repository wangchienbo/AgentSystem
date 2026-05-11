"""Phase B+E+D Component Wiring — assembles all core services into a unified orchestrator.

This module is the integration point that wires together:
- Phase B: SkillRpcService, UnifiedToolRegistry, ToolCallExecutor, CommandQueue
- Phase E: AssetCenter, ResourceCenter, ConfigCenter
- Phase D: MasterControlService, IntentRouter, ExecutionMonitor, AssetResourceQueryTools

Not a replacement for the existing AppOrchestrator — this is the NEW
architecture backbone that the existing code will gradually migrate to.
"""
from __future__ import annotations

import logging
from typing import Any

from app.runtime_paths import resolve_runtime_paths
from app.services.skill_rpc import SkillRpcService
from app.services.unified_tool_registry import UnifiedToolRegistry
from app.services.contract_linter import ContractLinter
from app.services.tool_loop_guard import ToolLoopGuard, ToolLoopConfig
from app.services.command_queue import CommandQueue
from app.services.tool_call_executor import ToolCallExecutor
from app.services.internal_model_router import InternalModelRouter
from app.services.resource_budget_manager import ResourceBudgetManager, ResourceBudgetConfig

from app.services.asset_center import AssetCenter
from app.services.resource_center import ResourceCenter
from app.services.config_center import ConfigCenterService

from app.services.master_control import MasterControlService
from app.services.execution_monitor import ExecutionMonitor
from app.services.intent_router import IntentRouter
from app.services.asset_resource_query_tools import AssetResourceQueryTools

logger = logging.getLogger(__name__)


class CoreOrchestrator:
    """Wiring layer for all Phase B+E+D components.

    Usage:
        orchestrator = CoreOrchestrator(data_dir="data")
        await orchestrator.initialize()
        result = await orchestrator.process_user_message(session_id, user_id, message)
    """

    def __init__(self, data_dir: str | None = None) -> None:
        self._data_dir = data_dir or str(resolve_runtime_paths().data_dir)

        # Phase B components
        self.skill_rpc = SkillRpcService()
        self.tool_registry = UnifiedToolRegistry()
        
        # Phase 3: ResourceBudgetManager for token/compute budget tracking
        self.resource_budget = ResourceBudgetManager(ResourceBudgetConfig())
        
        self.tool_executor = ToolCallExecutor(
            registry=self.tool_registry,
            tool_loop_guard=ToolLoopGuard(ToolLoopConfig()),
            contract_linter=ContractLinter(),
        )
        self.command_queue = CommandQueue()
        
        # Phase 3: Inject resource_budget into model_router
        self.model_router = InternalModelRouter(
            resource_budget=self.resource_budget,
        )

        # Phase E components
        self.asset_center = AssetCenter(data_dir=self._data_dir)
        self.resource_center = ResourceCenter(data_dir=self._data_dir)
        self.config_center = ConfigCenterService(data_dir=self._data_dir)

        # Phase D components
        self.master_control = MasterControlService(data_dir=self._data_dir)
        self.execution_monitor = ExecutionMonitor()
        self.intent_router = IntentRouter(
            execution_monitor=self.execution_monitor,
            command_queue=self.command_queue,
        )

        # Query tools (wired together)
        self.query_tools = AssetResourceQueryTools()

        self._initialized = False

    async def initialize(self) -> None:
        """Initialize all components in dependency order."""
        # 1. Config center (no deps)
        logger.info("Initializing config center...")

        # 2. Asset center — discover and index assets
        logger.info("Discovering assets...")
        self.asset_center.discover()

        # 3. Resource center — load existing instances
        logger.info("Initializing resource center...")

        # 4. Wire query tools
        self.query_tools.set_dependencies(
            asset_center=self.asset_center,
            asset_registry=self.asset_center,  # AssetCenter doubles as registry
            resource_center=self.resource_center,
        )

        # 5. Model router (already initialized with resource_budget in __init__)
        await self.model_router.initialize()

        # 6. Register system tools
        self._register_system_tools()

        # 7. Discover and register installed skills
        from app.services.skill_registry_service import SkillRegistryService
        skill_registry = SkillRegistryService(
            installed_dir="installed",
            rpc_service=self.skill_rpc,
            tool_registry=self.tool_registry,
        )
        skill_registry.discover_and_register()

        self._initialized = True
        logger.info("CoreOrchestrator initialized. Tools: %d", self.tool_registry.count())

    async def process_user_message(
        self,
        session_id: str,
        user_id: str,
        message: str,
    ) -> dict[str, Any]:
        """Process a user message through the full pipeline.

        1. Intent router classifies the message
        2. Simple commands handled directly
        3. Complex messages queued for LLM with full context
        """
        if not self._initialized:
            await self.initialize()

        return await self.intent_router.route(session_id, user_id, message)

    async def execute_tool_call(
        self,
        tool_id: str,
        arguments: dict[str, Any],
        caller_id: str | None = None,
    ) -> Any:
        """Execute a tool call through the unified executor."""
        return await self.tool_executor.call(tool_id, arguments, caller_id)

    async def call_model(
        self,
        prompt: str,
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Make a model API call through the serialized router.
        
        Args:
            prompt: User/system prompt
            system_prompt: Optional system prompt
            tools: Optional tool definitions for LLM function calling
            session_id: Session ID for budget tracking context
            user_id: User ID for budget tracking context
        """
        # Phase 3: Set context for budget tracking
        if session_id or user_id:
            self.model_router.set_context(session_id, user_id)
        
        return await self.model_router.call(
            prompt=prompt,
            system_prompt=system_prompt,
            tools=tools,
        )

    def get_visible_tools_for_llm(self, user_id: str, app_id: str | None = None) -> list[dict[str, Any]]:
        """Get visible tools formatted for LLM tool selection."""
        return self.tool_registry.list_for_llm(user_id=user_id, app_id=app_id)

    def get_candidates_for_llm(self, caller_id: str, user_id: str) -> dict[str, Any]:
        """Get full candidate set (assets + resources) for LLM context."""
        return self.query_tools.query_candidates(
            caller_id=caller_id,
            user_id=user_id,
            include_resources=True,
        )

    def _register_system_tools(self) -> None:
        """Register system-level fixed tools (query tools, etc.)."""
        # These are always available — no skill discovery needed
        from app.models.tool_entry import ToolEntry, ToolType, ToolVisibility

        query_tools = [
            ("query_visible_assets", "List assets visible to the caller"),
            ("query_asset_detail", "Get detailed information for a specific asset"),
            ("query_runtime_resources", "List current running resources"),
            ("query_resource_detail", "Get detail of a specific resource"),
        ]

        for tool_id, desc in query_tools:
            # These are bound dynamically at query time
            pass  # Registration happens via query_tools wrapper
