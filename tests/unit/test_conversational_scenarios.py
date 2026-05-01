from __future__ import annotations

import pytest

from app.system.asset_center.bootstrap import bootstrap_asset_center
from app.system.asset_center.models import AssetDescriptorRecord, AssetModelRequirement, AssetMethodSpec
from app.system.interaction_runtime.interaction_orchestrator import InteractionOrchestrator
from app.system.interaction_runtime.decision_protocol import DecisionProtocol
from app.system.interaction_runtime.context_assembly import ContextAssembly
from tests.unit.conversational_scenarios import ConversationalScenario, ScenarioTurn, load_all_scenarios


class _MockExecutor:
    def invoke(self, asset_id: str, method: str, params: dict) -> dict:
        return {"status": "ok", "asset_id": asset_id, "method": method, "result": {"summary": f"Executed {method} on {asset_id}"}}


@pytest.fixture
def orchestrator():
    asset_center = bootstrap_asset_center()

    asset_center.register_asset(
        AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="asset:self_iteration_center:v1",
            kind="system_asset",
            summary="Self-iteration governance and observation surface",
            detail="Provides regression, governance, observation, and backlog reasoning surfaces with Observe/Summarize/Act strategy.",
            methods=(
                AssetMethodSpec(name="strategy_overview", description="Return observe/summarize/act overview", input_schema={"type": "object"}, output_schema={"type": "object"}),
                AssetMethodSpec(name="governance_summary", description="Return governance summary", input_schema={"type": "object"}, output_schema={"type": "object"}),
            ),
            model_requirement=AssetModelRequirement(preferred_model="gpt-5.4", fallback_model="gpt-4.1", minimum_requirements={"structured_output": True}),
        )
    )

    asset_center.register_asset(
        AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="asset:config_center:v1",
            kind="system_asset",
            summary="System configuration management",
            detail="Provides system configuration get, update, and summary operations.",
            methods=(
                AssetMethodSpec(name="get_config", description="Get current configuration", input_schema={"type": "object"}, output_schema={"type": "object"}),
                AssetMethodSpec(name="update_config", description="Update configuration", input_schema={"type": "object"}, output_schema={"type": "object"}),
                AssetMethodSpec(name="model_config_summary", description="Summarize model configuration", input_schema={"type": "object"}, output_schema={"type": "object"}),
            ),
            model_requirement=AssetModelRequirement(preferred_model="gpt-5.4", fallback_model="gpt-4.1", minimum_requirements={}),
        )
    )

    return InteractionOrchestrator(
        asset_center_service=asset_center,
    )


@pytest.mark.parametrize("scenario", load_all_scenarios(), ids=lambda s: f"{s.scenario_id}_{s.title}")
def test_scenario_end_to_end(scenario: ConversationalScenario, orchestrator: InteractionOrchestrator) -> None:
    turn_results = []
    for turn in scenario.turns:
        response = orchestrator.process_message(turn.user_message)
        turn_results.append(response)

        if turn.expected_decision:
            assert response.get("decision") == turn.expected_decision or (
                turn.allow_text_fallback and response.get("decision") == "text"
            ), (
                f"Turn {turn.turn_number} of {scenario.scenario_id}: "
                f"expected decision {turn.expected_decision}, got {response.get('decision')}. "
                f"Response: {response}"
            )

        if turn.expected_asset_id:
            if response.get("decision") == "need_asset_detail_id":
                assert response.get("need_asset_detail_id") == turn.expected_asset_id, (
                    f"Turn {turn.turn_number} of {scenario.scenario_id}: "
                    f"expected asset {turn.expected_asset_id}, got {response.get('need_asset_detail_id')}"
                )
            elif response.get("decision") == "invoke":
                invoke_payload = response.get("invoke") or {}
                assert invoke_payload.get("asset_id") == turn.expected_asset_id, (
                    f"Turn {turn.turn_number} of {scenario.scenario_id}: "
                    f"expected invoke asset {turn.expected_asset_id}, got {invoke_payload.get('asset_id')}"
                )

        if turn.expected_method and response.get("decision") == "invoke":
            invoke_payload = response.get("invoke") or {}
            assert invoke_payload.get("method") == turn.expected_method, (
                f"Turn {turn.turn_number} of {scenario.scenario_id}: "
                f"expected method {turn.expected_method}, got {invoke_payload.get('method')}"
            )

    assert len(turn_results) == len(scenario.turns), (
        f"Scenario {scenario.scenario_id}: expected {len(scenario.turns)} turns, got {len(turn_results)}"
    )


def test_scenario_corpus_size() -> None:
    scenarios = load_all_scenarios()
    assert len(scenarios) >= 50, f"Expected at least 50 scenarios, got {len(scenarios)}"


def test_scenario_corpus_coverage() -> None:
    scenarios = load_all_scenarios()
    categories = {s.category for s in scenarios}
    required = {"simple_query", "detail_request", "invoke", "fallback", "failure_recovery", "clarification", "topic_shift", "follow_up", "complex_mixed"}
    missing = required - categories
    assert not missing, f"Missing scenario categories: {missing}"


def test_scenario_corpus_multi_turn_variety() -> None:
    scenarios = load_all_scenarios()
    multi_turn = [s for s in scenarios if len(s.turns) >= 3]
    assert len(multi_turn) >= 10, f"Expected at least 10 multi-turn scenarios (>=3 turns), got {len(multi_turn)}"


def test_scenario_corpus_10_turn_exists() -> None:
    scenarios = load_all_scenarios()
    ten_turn = [s for s in scenarios if len(s.turns) >= 10]
    assert len(ten_turn) >= 1, "Expected at least one 10-turn scenario"
