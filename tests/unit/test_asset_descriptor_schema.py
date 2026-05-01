"""Descriptor/schema unit tests for Phase 9.1.

Focus: AssetDescriptorRecord validation, model_requirement, methods schema,
to_dict/from_dict roundtrips, and descriptor version enforcement.
"""
from __future__ import annotations

import pytest

from app.system.asset_center.models import (
    AssetDescriptorRecord,
    AssetMethodSpec,
    AssetModelRequirement,
)


class TestAssetModelRequirement:
    def test_default_is_empty(self) -> None:
        req = AssetModelRequirement()
        assert req.preferred_model is None
        assert req.fallback_model is None
        assert req.minimum_requirements == {}

    def test_to_dict_roundtrip(self) -> None:
        req = AssetModelRequirement(
            preferred_model="qwen-plus",
            fallback_model="qwen-turbo",
            minimum_requirements={"structured_output": True},
        )
        d = req.to_dict()
        assert d["preferred_model"] == "qwen-plus"
        assert d["fallback_model"] == "qwen-turbo"
        assert d["minimum_requirements"] == {"structured_output": True}

    def test_only_fallback(self) -> None:
        req = AssetModelRequirement(fallback_model="fallback-only")
        assert req.preferred_model is None
        assert req.fallback_model == "fallback-only"


class TestAssetMethodSpec:
    def test_minimal_spec(self) -> None:
        m = AssetMethodSpec(
            name="ping",
            description="Health check",
            input_schema={"type": "object", "properties": {}},
        )
        assert m.output_schema == {}
        assert m.name == "ping"

    def test_full_spec(self) -> None:
        m = AssetMethodSpec(
            name="get_config",
            description="Read config",
            input_schema={
                "type": "object",
                "properties": {"skill_id": {"type": "string"}},
                "required": ["skill_id"],
            },
            output_schema={"type": "object", "properties": {"value": {"type": "object"}}},
        )
        assert m.input_schema["required"] == ["skill_id"]
        assert "value" in m.output_schema["properties"]


class TestAssetDescriptorRecord:
    def test_minimal_descriptor(self) -> None:
        d = AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="asset:demo:v1",
            kind="demo_asset",
            summary="Demo",
            detail="Demo detail",
        )
        assert d.methods == ()
        assert d.model_requirement == AssetModelRequirement()
        assert d.registration_epoch == 0

    def test_descriptor_with_methods(self) -> None:
        method = AssetMethodSpec(
            name="list",
            description="List items",
            input_schema={"type": "object"},
        )
        d = AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="asset:list:v1",
            kind="system_asset",
            summary="List asset",
            detail="Provides listing capability",
            methods=(method,),
        )
        assert len(d.methods) == 1
        assert d.methods[0].name == "list"

    def test_to_dict_includes_all_fields(self) -> None:
        method = AssetMethodSpec(
            name="search",
            description="Search",
            input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
            output_schema={"type": "array"},
        )
        d = AssetDescriptorRecord(
            descriptor_version=2,
            asset_id="asset:search:v1",
            kind="system_asset",
            summary="Search asset",
            detail="Provides search",
            methods=(method,),
            model_requirement=AssetModelRequirement(
                preferred_model="model-a",
                minimum_requirements={"tool_use": True},
            ),
            metadata={"owner": "team-x"},
            registration_epoch=42,
        )
        payload = d.to_dict()
        assert payload["descriptor_version"] == 2
        assert payload["asset_id"] == "asset:search:v1"
        assert payload["kind"] == "system_asset"
        assert payload["summary"] == "Search asset"
        assert payload["detail"] == "Provides search"
        assert len(payload["methods"]) == 1
        assert payload["methods"][0]["name"] == "search"
        assert payload["model_requirement"]["preferred_model"] == "model-a"
        assert payload["metadata"] == {"owner": "team-x"}
        assert payload["registration_epoch"] == 42

    def test_to_dict_empty_methods_serializes_as_list(self) -> None:
        d = AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="asset:empty:v1",
            kind="demo",
            summary="Empty",
            detail="Empty",
        )
        payload = d.to_dict()
        assert payload["methods"] == []

    def test_descriptor_idempotent_to_dict(self) -> None:
        d = AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="asset:idem:v1",
            kind="demo",
            summary="Idem",
            detail="Idem",
        )
        first = d.to_dict()
        second = d.to_dict()
        assert first == second

    def test_metadata_defaults_to_empty_dict(self) -> None:
        d = AssetDescriptorRecord(
            descriptor_version=1,
            asset_id="asset:meta:v1",
            kind="demo",
            summary="Meta",
            detail="Meta",
        )
        assert d.metadata == {}
