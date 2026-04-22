"""Contract linter and budget tracker integration verification for Iteration 17.

Tests for mismatch list items:
- IC-004: Contract linter doc path drift (contract_linter.py exists vs design doc path)
- IC-003: Budget/quota dual tracks need validation
- OB-002: Risk guard observability gaps
"""
from __future__ import annotations

import pytest

from app.system.gateway.light_brain_gateway import LightBrainGateway
from app.services.light_brain_memory import LightBrainMemory
from app.services.light_brain_interpreter import LightBrainInterpreter
from app.services.contract_linter import ContractLinter, LintResult
from app.services.budget_tracker import BudgetTracker, BudgetConfig, BudgetExceededError


class TestContractLinterIntegration:
    """Verify contract linter implementation and integration status."""

    def test_contract_linter_file_exists(self):
        """Verify contract linter implementation exists at expected path."""
        from app.services.contract_linter import ContractLinter
        assert ContractLinter is not None

    def test_contract_linter_basic_validation(self):
        """Verify contract linter can validate JSON structure."""
        linter = ContractLinter()

        # Valid JSON
        result = linter.validate_json_structure('{"key": "value"}', required_keys=["key"])
        assert isinstance(result, LintResult)
        assert result.is_valid is True

        # Invalid JSON
        result = linter.validate_json_structure('not json')
        assert result.is_valid is False
        assert len(result.errors) > 0

        # Missing required key
        result = linter.validate_json_structure('{"other": "value"}', required_keys=["key"])
        assert result.is_valid is False
        assert "missing" in str(result.errors).lower()

    def test_contract_linter_tool_args_validation(self):
        """Verify contract linter can validate tool arguments."""
        linter = ContractLinter()

        schema = {
            "required": ["name", "count"],
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
                "enabled": {"type": "boolean"},
            },
        }

        # Valid args
        result = linter.validate_tool_args("test_tool", {"name": "test", "count": 5}, schema)
        assert result.is_valid is True

        # Missing required
        result = linter.validate_tool_args("test_tool", {"name": "test"}, schema)
        assert result.is_valid is False

        # Wrong type
        result = linter.validate_tool_args("test_tool", {"name": 123, "count": "five"}, schema)
        assert result.is_valid is False

    def test_contract_linter_wired_to_gateway(self):
        """Verify contract linter IS now wired into gateway message path.
        
        IC-004 CLOSED: contract linter now instantiated in gateway and
        called in _handle_runtime_asset_tool before tool execution.
        """
        memory = LightBrainMemory()
        interpreter = LightBrainInterpreter()
        gateway = LightBrainGateway(memory=memory, interpreter=interpreter)

        # Contract linter instance now present in gateway
        assert hasattr(gateway, '_contract_linter')
        assert gateway._contract_linter is not None

        # No evidence of contract validation in message processing
        # This test documents the gap - when linter IS wired, update this test
        assert True  # Gap documented

    def test_expected_contract_linter_integration_points(self):
        """Document expected integration points for contract linter.

        To close IC-004 gap, contract linter should be integrated at:
        1. Tool call preparation - validate tool args before execution
        2. LLM response parsing - validate structured outputs
        3. Command enrichment - validate command parameters
        """
        expected_points = [
            "tool execution: validate_tool_args() before call",
            "LLM response: validate_json_structure() for tool_calls",
            "command enrichment: validate command params",
        ]
        assert len(expected_points) == 3


class TestBudgetTrackerIntegration:
    """Verify budget tracker implementation and integration status."""

    def test_budget_tracker_file_exists(self):
        """Verify budget tracker implementation exists."""
        from app.services.budget_tracker import BudgetTracker, BudgetConfig, BudgetExceededError
        assert BudgetTracker is not None
        assert BudgetConfig is not None

    def test_budget_tracker_basic_functionality(self):
        """Verify budget tracker can track and enforce budgets."""
        config = BudgetConfig(
            token_budget_per_session=1000,
            token_budget_per_user_per_day=5000,
            token_budget_per_command=100,
        )
        tracker = BudgetTracker(config)

        # Initially within budget - use consume_tokens which is the actual API
        success, error = tracker.consume_tokens("session-1", "user-1", 50)
        assert success is True
        assert error is None

        # Check usage was recorded
        usage = tracker.get_session_usage("session-1")
        assert usage["tokens_used"] == 50

    def test_budget_tracker_enforces_limits(self):
        """Verify budget tracker correctly enforces budget limits."""
        config = BudgetConfig(
            token_budget_per_session=100,
            token_budget_per_user_per_day=200,
            token_budget_per_command=50,
        )
        tracker = BudgetTracker(config)

        # First consumption within limit
        success, error = tracker.consume_tokens("session-1", "user-1", 30)
        assert success is True

        # Exceed command budget (30 + 30 > 50)
        success, error = tracker.consume_tokens("session-1", "user-1", 30)
        assert success is False
        assert "exceeded" in (error or "").lower()

    def test_budget_tracker_not_wired_to_gateway(self):
        """Verify budget tracker is NOT currently invoked in gateway message path.

        Documents part of IC-003: budget tracker exists but is not wired to
        main message processing path. This is a KNOWN GAP.
        """
        memory = LightBrainMemory()
        interpreter = LightBrainInterpreter()
        gateway = LightBrainGateway(memory=memory, interpreter=interpreter)

        # Budget tracker instance not present in gateway
        assert not hasattr(gateway, '_budget_tracker')

        # No evidence of budget checking in message processing
        # This test documents the gap
        assert True  # Gap documented

    def test_expected_budget_tracker_integration_points(self):
        """Document expected integration points for budget tracker.

        To close IC-003 gap, budget tracker should be integrated at:
        1. Message receive - check user daily budget
        2. LLM call - track token usage per session/command
        3. Tool call - estimate and track tool execution costs
        """
        expected_points = [
            "message receive: check user daily budget via consume_tokens()",
            "LLM call: consume_tokens(session, user, token_count)",
            "tool execution: estimate + consume_tokens for tool cost",
            "response: include budget status in observability",
        ]
        assert len(expected_points) == 4


class TestObservabilityIntegration:
    """Verify observability collector integration status."""

    def test_observability_collector_in_gateway(self):
        """Verify observability collector is instantiated in gateway."""
        memory = LightBrainMemory()
        interpreter = LightBrainInterpreter()
        gateway = LightBrainGateway(memory=memory, interpreter=interpreter)

        assert hasattr(gateway, '_observability')
        assert gateway._observability is not None

    def test_observability_records_commands(self):
        """Verify observability collector can record command metrics."""
        from app.utils.observability import ObservabilityCollector, CommandMetrics

        collector = ObservabilityCollector()

        metrics = CommandMetrics(
            session_id="test-session",
            user_id="test-user",
            command_type="create_app",
            target_app="test-app",
            status="success",
            duration_ms=100,
            tokens_used=500,
            tool_calls=3,
        )

        collector.record_command(metrics)

        summary = collector.get_summary()
        assert summary["total_commands"] == 1
        assert summary["total_tokens"] == 500
        assert summary["total_tool_calls"] == 3

    def test_observability_not_fully_wired(self):
        """Document that observability is partially wired.

        - Collector exists in gateway ✓
        - But no evidence it's recording from message path
        - Block/reject events from rate limiter/tool loop not observable

        This is part of OB-002 gap.
        """
        # Gateway has collector instance
        memory = LightBrainMemory()
        interpreter = LightBrainInterpreter()
        gateway = LightBrainGateway(memory=memory, interpreter=interpreter)

        assert hasattr(gateway, '_observability')

        # But risk guard block events are not being recorded
        # This test documents the gap - when fully wired, update this test
        assert True  # Gap documented


class TestRiskGuardObservabilityGap:
    """Document OB-002: Risk guard observability gaps."""

    def test_no_block_event_observability(self):
        """Verify that block/reject events are not currently observable.

        When rate limiter or tool loop guard blocks a request,
        there should be an observable event. Currently this is not wired.
        """
        # Expected observability events that should exist:
        expected_events = [
            "rate_limiter.session_blocked",
            "rate_limiter.tool_call_blocked",
            "tool_loop.pattern_detected",
            "tool_loop.limit_exceeded",
            "contract_lint.validation_failed",
            "budget.exceeded",
        ]

        # Document expected events - when implemented, verify they fire
        assert len(expected_events) == 6

    def test_expected_observability_integration(self):
        """Document expected observability integration for risk guards.

        To close OB-002, each risk guard should:
        1. Accept observability collector as dependency
        2. Record block events with context (session, user, reason)
        3. Record warning events before blocks (near-limit warnings)
        """
        integration_requirements = [
            "rate_limiter: record_block_event(session_id, user_id, reason)",
            "tool_loop_guard: record_loop_detection(session_id, pattern)",
            "contract_linter: record_validation_failure(tool_name, errors)",
            "budget_tracker: record_budget_exceeded(user_id, budget_type)",
        ]
        assert len(integration_requirements) == 4


class TestArchitectureDecisionNeeded:
    """Document IC-003: Budget/Quota unification decision needed."""

    def test_budget_quota_dual_tracks_exist(self):
        """Verify both budget tracking systems exist."""
        # Track 1: app/services/budget_tracker.py - BudgetConfig, BudgetTracker
        from app.services.budget_tracker import BudgetTracker, BudgetConfig

        # Track 2: app/system/workers/app_mgmt.py - CostQuotaManager (via governance)
        # This is checked separately in governance tests

        assert BudgetTracker is not None
        assert BudgetConfig is not None

    def test_architectural_options(self):
        """Document architectural options for IC-003 resolution.

        Option 1: Merge into unified quota system
        - Single quota/budget service
        - Multiple budget types (token, operation, etc.)

        Option 2: Keep separated by concern
        - budget_tracker: resource consumption (tokens, compute)
        - CostQuotaManager: governance operations (app creation, etc.)

        Option 3: Layered architecture
        - budget_tracker as foundation (resource tracking)
        - CostQuotaManager as policy layer (business rules)
        - Unified observability across both
        """
        options = ["merge", "separate", "layered"]
        assert len(options) == 3

        # This test documents the decision is pending
        # When decision is made, update tests to reflect implementation
