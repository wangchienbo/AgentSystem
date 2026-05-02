from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.app_context_store import AppContextStore
from app.services.app_data_store import AppDataStore
from app.services.app_installer import AppInstallerError, AppInstallerService
from app.services.app_registry import AppRegistryService
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore


class _DummyAssetCenter:
    def __init__(self) -> None:
        self._source_dir = None


def _build_installer(tmp_path) -> AppInstallerService:
    lifecycle = AppLifecycleService()
    store = RuntimeStateStore(base_dir=str(tmp_path / "runtime-state"))
    runtime_host = AppRuntimeHostService(lifecycle)
    return AppInstallerService(
        registry=AppRegistryService(),
        lifecycle=lifecycle,
        runtime_host=runtime_host,
        data_store=AppDataStore(base_dir=str(tmp_path / "data-store"), store=store),
        context_store=AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime_host),
    )


def test_installer_manifest_compliance_accepts_phase_p_metadata(tmp_path) -> None:
    installer = _build_installer(tmp_path)
    manifest = {
        "asset_id": "app.demo",
        "asset_type": "app",
        "name": "Demo",
        "version": "1.0.0",
        "entry": "blueprint.json",
        "owner": "system",
        "owner_role": "admin",
        "dependencies": [],
        "source_path": "source/app.demo",
        "description": "demo",
        "metadata": {
            "invocation_contract_version": "phase-p-v1",
            "runtime_wrapper_compatibility": True,
            "session_binding_support": "required",
            "endpoint_requirement": "optional",
            "tool_vllm_usage_mode": "session_binding_resolved",
        },
    }

    installer._validate_manifest_compliance(manifest)


def test_installer_manifest_compliance_rejects_non_compliant_metadata(tmp_path) -> None:
    installer = _build_installer(tmp_path)
    manifest = {
        "asset_id": "app.demo",
        "asset_type": "app",
        "name": "Demo",
        "version": "1.0.0",
        "entry": "blueprint.json",
        "owner": "system",
        "owner_role": "admin",
        "dependencies": [],
        "source_path": "source/app.demo",
        "description": "demo",
        "metadata": {
            "invocation_contract_version": "legacy",
            "runtime_wrapper_compatibility": False,
        },
    }

    with pytest.raises(AppInstallerError, match="invocation compliance validation failed"):
        installer._validate_manifest_compliance(manifest)
