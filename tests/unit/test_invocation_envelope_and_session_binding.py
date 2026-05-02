from __future__ import annotations

import pytest

from app.system.asset_center.models import AssetSessionBindingRecord
from app.system.asset_center.registry import AssetCenterRegistry
from app.system.asset_center.service import AssetCenterService
from app.system.invocation.invocation_envelope import (
    InvocationCallerRef,
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


class TestInvocationResponseEnvelope:
    def test_validate_minimal(self) -> None:
        env = InvocationResponseEnvelope(ok=True, request_id="req-1")
        env.validate()

    def test_validate_requires_request_id(self) -> None:
        with pytest.raises(ValueError):
            InvocationResponseEnvelope(ok=True, request_id="").validate()


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
        got = service.get_session_binding("asset:test:v1", "up-2")
        listed = service.list_session_bindings("asset:test:v1")
        assert got is not None
        assert got.local_session_id == "loc-2"
        assert len(listed) == 1
        assert listed[0]["upstream_session_id"] == "up-2"
