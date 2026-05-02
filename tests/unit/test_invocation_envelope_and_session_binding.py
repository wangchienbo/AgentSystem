from __future__ import annotations

import pytest

from app.system.asset_center.models import AssetSessionBindingRecord
from app.system.asset_center.registry import AssetCenterRegistry
from app.system.asset_center.service import AssetCenterService
from app.system.invocation.invocation_envelope import (
    InvocationCallerRef,
    InvocationErrorTaxonomy,
    InvocationRequestEnvelope,
    InvocationResponseEnvelope,
    InvocationSessionRef,
)


class TestInvocationSessionRef:
    def test_validate_requires_upstream_session_id(self) -> None:
        with pytest.raises(ValueError):
            InvocationSessionRef(upstream_session_id="").validate()

    def test_to_dict(self) -> None:
        ref = InvocationSessionRef(
            upstream_session_id="sess-up-1",
            root_session_id="root-1",
            parent_session_id="parent-1",
        )
        assert ref.to_dict()["upstream_session_id"] == "sess-up-1"


class TestInvocationRequestEnvelope:
    def test_validate_minimal(self) -> None:
        env = InvocationRequestEnvelope(
            request_id="req-1",
            target_id="asset:test:v1",
            target_type="system_asset",
            method="ping",
        )
        env.validate()

    def test_validate_rejects_non_dict_args(self) -> None:
        env = InvocationRequestEnvelope(
            request_id="req-1",
            target_id="asset:test:v1",
            target_type="system_asset",
            method="ping",
            args=None,  # type: ignore[arg-type]
        )
        with pytest.raises(ValueError):
            env.validate()

    def test_from_legacy(self) -> None:
        env = InvocationRequestEnvelope.from_legacy(
            asset_id="asset:legacy:v1",
            method="ping",
            params={"x": 1},
        )
        assert env.target_id == "asset:legacy:v1"
        assert env.args == {"x": 1}

    def test_normalize_legacy_payload(self) -> None:
        env = InvocationRequestEnvelope.normalize_legacy(
            {"asset_id": "asset:legacy:v1", "method": "ping", "params": {"x": 2}, "request_id": "req-2"}
        )
        assert env.request_id == "req-2"
        assert env.args == {"x": 2}

    def test_round_trip_from_dict(self) -> None:
        env = InvocationRequestEnvelope.from_dict(
            {
                "request_id": "req-1",
                "target_id": "asset:test:v1",
                "target_type": "system_asset",
                "method": "ping",
                "args": {"x": 1},
                "session": {"upstream_session_id": "up-1", "root_session_id": "root-1"},
                "caller": {"caller_id": "control", "caller_type": "system"},
            }
        )
        env.validate()
        assert env.session is not None
        assert env.caller is not None
        assert env.to_dict()["session"]["root_session_id"] == "root-1"


class TestInvocationErrorTaxonomy:
    def test_validate_minimal(self) -> None:
        taxonomy = InvocationErrorTaxonomy(code="params_schema_mismatch", category="validation")
        taxonomy.validate()

    def test_to_from_dict(self) -> None:
        taxonomy = InvocationErrorTaxonomy(
            code="binding_missing",
            category="binding",
            message="binding not found",
            retryable=True,
            metadata={"asset_id": "asset:test:v1"},
        )
        restored = InvocationErrorTaxonomy.from_dict(taxonomy.to_dict())
        assert restored.code == "binding_missing"
        assert restored.retryable is True


class TestInvocationResponseEnvelope:
    def test_validate_minimal(self) -> None:
        env = InvocationResponseEnvelope(ok=True, request_id="req-1")
        env.validate()

    def test_validate_requires_request_id(self) -> None:
        with pytest.raises(ValueError):
            InvocationResponseEnvelope(ok=True, request_id="").validate()

    def test_round_trip_with_error_taxonomy(self) -> None:
        env = InvocationResponseEnvelope(
            ok=False,
            request_id="req-err",
            error="bad params",
            error_type="params_schema_mismatch",
            error_taxonomy=InvocationErrorTaxonomy(
                code="params_schema_mismatch",
                category="validation",
                message="bad params",
            ),
        )
        data = env.to_dict()
        restored = InvocationResponseEnvelope.from_dict(data)
        restored.validate()
        assert restored.error_taxonomy is not None
        assert restored.error_taxonomy.category == "validation"


class TestAssetSessionBindingRecord:
    def test_validate_requires_ids(self) -> None:
        with pytest.raises(ValueError):
            AssetSessionBindingRecord(
                asset_id="",
                upstream_session_id="up-1",
                local_session_id="loc-1",
            ).validate()

    def test_to_dict(self) -> None:
        record = AssetSessionBindingRecord(
            asset_id="asset:test:v1",
            upstream_session_id="up-1",
            local_session_id="loc-1",
        )
        assert record.to_dict()["local_session_id"] == "loc-1"

    def test_from_dict_round_trip(self) -> None:
        data = {
            "asset_id": "asset:test:v1",
            "upstream_session_id": "up-1",
            "local_session_id": "loc-1",
            "root_session_id": "root-1",
            "parent_session_id": "parent-1",
            "status": "active",
            "created_at": "2026-05-02T00:00:00+00:00",
            "last_active_at": "2026-05-02T00:01:00+00:00",
            "metadata": {"k": "v"},
        }
        record = AssetSessionBindingRecord.from_dict(data)
        assert record.to_dict() == data


class TestAssetSessionBindingStore:
    def test_upsert_and_get_binding(self) -> None:
        registry = AssetCenterRegistry()
        record = AssetSessionBindingRecord(
            asset_id="asset:test:v1",
            upstream_session_id="up-1",
            local_session_id="loc-1",
        )
        stored = registry.upsert_session_binding(record)
        got = registry.get_session_binding("asset:test:v1", "up-1")
        assert stored.local_session_id == "loc-1"
        assert got is not None
        assert got.local_session_id == "loc-1"

    def test_uniqueness_violation_raises(self) -> None:
        registry = AssetCenterRegistry()
        registry.upsert_session_binding(
            AssetSessionBindingRecord(
                asset_id="asset:test:v1",
                upstream_session_id="up-1",
                local_session_id="loc-1",
            )
        )
        with pytest.raises(ValueError):
            registry.upsert_session_binding(
                AssetSessionBindingRecord(
                    asset_id="asset:test:v1",
                    upstream_session_id="up-1",
                    local_session_id="loc-2",
                )
            )

    def test_service_exposes_binding_apis(self) -> None:
        service = AssetCenterService(registry=AssetCenterRegistry())
        service.upsert_session_binding(
            AssetSessionBindingRecord(
                asset_id="asset:test:v1",
                upstream_session_id="up-2",
                local_session_id="loc-2",
            )
        )
        service.upsert_session_binding(
            AssetSessionBindingRecord(
                asset_id="asset:test:v1",
                upstream_session_id="up-3",
                local_session_id="loc-3",
            )
        )
        got = service.get_session_binding("asset:test:v1", "up-2")
        listed = service.list_session_bindings("asset:test:v1")
        recent = service.list_recent_session_bindings("asset:test:v1", limit=1)
        assert got is not None
        assert got.local_session_id == "loc-2"
        assert len(listed) == 2
        assert len(recent) == 1
