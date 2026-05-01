from __future__ import annotations

import pytest

from app.models.asset_contract import AssetCapability, AssetDescriptor, AssetKind, AssetState, AssetType
from app.system.asset_center.models import AssetDescriptorRecord, AssetMethodSpec, AssetModelRequirement, InteractionDecisionEnvelope
from app.system.asset_center.service import AssetCenterService
from app.system.catalog.runtime_center import RuntimeCenter
from app.system.invocation.invocation_dispatcher import InvocationDispatchError, InvocationDispatcher
from app.system.model_runtime.model_client_registry import ModelRuntimeRecord


def _build_dispatcher(tmp_path) -> tuple[AssetCenterService, RuntimeCenter, InvocationDispatcher]:
    asset_center = AssetCenterService()
    runtime_center = RuntimeCenter(data_file=str(tmp_path / "runtime_center.json"))
    dispatcher = InvocationDispatcher(asset_center=asset_center, runtime_center=runtime_center)
    return asset_center, runtime_center, dispatcher


def test_invocation_dispatcher_prepares_call_with_resolved_model(tmp_path) -> None:
    asset_center, runtime_center, dispatcher = _build_dispatcher(tmp_path)
    asset_center.register_asset(
        AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="asset:config_center:v1",
            kind="system_asset",
            summary="Config center",
            detail="Read config",
            methods=(
                AssetMethodSpec(
                    name="get_config",
                    description="Read config",
                    input_schema={
                        "type": "object",
                        "properties": {"skill_id": {"type": "string"}},
                        "required": ["skill_id"],
                        "additionalProperties": False,
                    },
                ),
            ),
            model_requirement=AssetModelRequirement(
                preferred_model="gpt-5.4",
                fallback_model="gpt-4.1",
                minimum_requirements={"structured_output": True},
            ),
        )
    )
    asset_center.register_model(
        ModelRuntimeRecord(
            model_id="gpt-5.4",
            provider="OpenAICompatible",
            base_url="https://example.invalid/v1",
            api_key_env="OPENAI_API_KEY",
            wire_api="openai-responses",
            enabled=True,
            healthy=True,
            metadata={"structured_output": True},
        )
    )

    prepared = dispatcher.prepare_call(
        asset_id="asset:config_center:v1",
        method="get_config",
        params={"skill_id": "maoxuan_skill"},
    )

    assert prepared.resolved_model is not None
    assert prepared.resolved_model.model_id == "gpt-5.4"
    assert prepared.method == "get_config"


def test_invocation_dispatcher_rejects_missing_required_param(tmp_path) -> None:
    asset_center, runtime_center, dispatcher = _build_dispatcher(tmp_path)
    asset_center.register_asset(
        AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="asset:config_center:v1",
            kind="system_asset",
            summary="Config center",
            detail="Read config",
            methods=(
                AssetMethodSpec(
                    name="get_config",
                    description="Read config",
                    input_schema={
                        "type": "object",
                        "properties": {"skill_id": {"type": "string"}},
                        "required": ["skill_id"],
                        "additionalProperties": False,
                    },
                ),
            ),
        )
    )

    with pytest.raises(InvocationDispatchError, match="missing required param") as exc_info:
        dispatcher.prepare_call(asset_id="asset:config_center:v1", method="get_config", params={})
    assert exc_info.value.error_type == "params_schema_mismatch"


def test_invocation_dispatcher_rejects_undeclared_method(tmp_path) -> None:
    asset_center, runtime_center, dispatcher = _build_dispatcher(tmp_path)
    asset_center.register_asset(
        AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="asset:config_center:v1",
            kind="system_asset",
            summary="Config center",
            detail="Read config",
            methods=(),
        )
    )

    with pytest.raises(InvocationDispatchError, match="not declared") as exc_info:
        dispatcher.prepare_call(asset_id="asset:config_center:v1", method="get_config", params={})
    assert exc_info.value.error_type == "method_not_declared"


def test_invocation_dispatcher_safe_dispatch_surfaces_model_selection_failure(tmp_path) -> None:
    asset_center, runtime_center, dispatcher = _build_dispatcher(tmp_path)
    asset_center.register_asset(
        AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="asset:config_center:v1",
            kind="system_asset",
            summary="Config center",
            detail="Read config",
            methods=(
                AssetMethodSpec(
                    name="get_config",
                    description="Read config",
                    input_schema={"type": "object", "properties": {}},
                ),
            ),
            model_requirement=AssetModelRequirement(
                preferred_model="gpt-5.4",
                fallback_model="gpt-4.1",
                minimum_requirements={"structured_output": True},
            ),
        )
    )
    asset_center.register_model(
        ModelRuntimeRecord(
            model_id="gpt-4.1",
            provider="OpenAICompatible",
            base_url="https://example.invalid/v1",
            api_key_env="OPENAI_API_KEY",
            wire_api="openai-responses",
            enabled=True,
            healthy=True,
            metadata={"structured_output": False},
        )
    )

    result = dispatcher.safe_dispatch(asset_id="asset:config_center:v1", method="get_config", params={})

    assert result["ok"] is False
    assert result["error_type"] == "model_selection_failed"


def test_invocation_dispatcher_dispatches_to_runtime_center(tmp_path) -> None:
    asset_center, runtime_center, dispatcher = _build_dispatcher(tmp_path)
    asset_center.register_asset(
        AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="asset:config_center:v1",
            kind="system_asset",
            summary="Config center",
            detail="Read config",
            methods=(
                AssetMethodSpec(
                    name="get_config",
                    description="Read config",
                    input_schema={
                        "type": "object",
                        "properties": {"skill_id": {"type": "string"}},
                        "required": ["skill_id"],
                    },
                ),
            ),
        )
    )
    runtime_center.register_asset(
        AssetDescriptor(
            asset_id="asset:config_center:v1",
            asset_type=AssetType.SERVICE,
            asset_kind=AssetKind.CORE_RUNTIME,
            version="1.0.0",
            owner_type="system",
            owner_id="system",
            source_of_truth="runtime",
            status=AssetState.ACTIVE,
            capabilities=[
                AssetCapability(name="get config", description="Read config", method="get_config", side_effect_level="read")
            ],
            invoke_contract={"kind": "service"},
            health_contract={"heartbeat": False},
            name="config_center",
            description="Config center",
        ),
        method_mappings={"get_config": lambda skill_id=None: {"skill_config": {"skill_id": skill_id}}},
    )

    result = dispatcher.dispatch(
        asset_id="asset:config_center:v1",
        method="get_config",
        params={"skill_id": "maoxuan_skill"},
    )

    assert result["ok"] is True
    assert result["execution"]["result"]["skill_config"]["skill_id"] == "maoxuan_skill"
    assert result["resolved_call"]["method"] == "get_config"


def test_invocation_dispatcher_dispatches_from_self_iteration_envelope(tmp_path) -> None:
    asset_center, runtime_center, dispatcher = _build_dispatcher(tmp_path)
    asset_center.register_asset(
        AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="asset:self_iteration_center:v1",
            kind="system_asset",
            summary="Self iteration",
            detail="Governance asset",
            methods=(
                AssetMethodSpec(
                    name="list_self_iteration_assets",
                    description="List self iteration assets",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "comparison_limit": {"type": "integer"},
                        },
                    },
                ),
            ),
        )
    )
    runtime_center.register_asset(
        AssetDescriptor(
            asset_id="asset:self_iteration_center:v1",
            asset_type=AssetType.SERVICE,
            asset_kind=AssetKind.CORE_RUNTIME,
            version="1.0.0",
            owner_type="system",
            owner_id="system",
            source_of_truth="runtime",
            status=AssetState.ACTIVE,
            capabilities=[
                AssetCapability(
                    name="list self iteration assets",
                    description="List self iteration assets",
                    method="list_self_iteration_assets",
                    side_effect_level="read",
                )
            ],
            invoke_contract={"kind": "service"},
            health_contract={"heartbeat": False},
            name="self_iteration_center",
            description="Self iteration",
        ),
        method_mappings={"list_self_iteration_assets": lambda comparison_limit=5: [{"asset_id": "asset:config_center:v1", "rank": 1, "comparison_limit": comparison_limit}]},
    )

    result = dispatcher.dispatch_from_envelope(
        InteractionDecisionEnvelope(
            decision="invoke",
            invoke={
                "asset_id": "asset:self_iteration_center:v1",
                "method": "list_self_iteration_assets",
                "params": {"comparison_limit": 3},
            },
        )
    )

    assert result["ok"] is True
    assert result["resolved_call"]["asset_id"] == "asset:self_iteration_center:v1"
    assert result["execution"]["result"][0]["comparison_limit"] == 3
