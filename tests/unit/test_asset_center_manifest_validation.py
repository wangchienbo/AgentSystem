from __future__ import annotations

import json

import pytest

from app.system.catalog.asset_center import AssetCenter


def _valid_manifest() -> dict:
    return {
        "asset_id": "system.master",
        "asset_type": "system",
        "name": "Master Control",
        "version": "1.0.0",
        "entry": "main.py",
        "owner": "system",
        "owner_role": "system",
        "dependencies": [],
        "source_path": "source/system.master",
        "description": "system",
        "metadata": {
            "invocation_contract_version": "phase-p-v1",
            "runtime_wrapper_compatibility": True,
            "session_binding_support": "supported",
            "endpoint_requirement": "none",
            "tool_vllm_usage_mode": "local_session_only",
        },
    }


@pytest.mark.parametrize(
    ("missing_field", "expected_message"),
    [
        ("asset_id", "missing required manifest fields"),
        ("asset_type", "missing required manifest fields"),
        ("entry", "missing required manifest fields"),
        ("owner", "missing required manifest fields"),
        ("owner_role", "missing required manifest fields"),
        ("dependencies", "missing required manifest fields"),
        ("metadata", "missing required manifest fields"),
    ],
)
def test_discover_skips_manifest_missing_required_fields(tmp_path, missing_field: str, expected_message: str) -> None:
    source_dir = tmp_path / "source"
    asset_dir = source_dir / "system.master"
    asset_dir.mkdir(parents=True)

    manifest = _valid_manifest()
    manifest.pop(missing_field)
    (asset_dir / "manifest.json").write_text(__import__("json").dumps(manifest), encoding="utf-8")

    center = AssetCenter(
        source_dir=str(source_dir),
        installed_dir=str(tmp_path / "installed"),
        build_dir=str(tmp_path / "build"),
        data_dir=str(tmp_path / "data"),
    )

    assets = center.discover()

    assert assets == []
    assert center.get_asset("system.master") is None


def test_discover_skips_manifest_with_mismatched_asset_identity(tmp_path) -> None:
    source_dir = tmp_path / "source"
    asset_dir = source_dir / "system.master"
    asset_dir.mkdir(parents=True)
    (asset_dir / "manifest.json").write_text(
        json.dumps({**_valid_manifest(), "asset_id": "system.gateway"}),
        encoding="utf-8",
    )

    center = AssetCenter(
        source_dir=str(source_dir),
        installed_dir=str(tmp_path / "installed"),
        build_dir=str(tmp_path / "build"),
        data_dir=str(tmp_path / "data"),
    )

    assets = center.discover()

    assert assets == []
    assert center.get_asset("system.gateway") is None


def test_discover_accepts_valid_manifest(tmp_path) -> None:
    source_dir = tmp_path / "source"
    asset_dir = source_dir / "system.master"
    asset_dir.mkdir(parents=True)
    (asset_dir / "manifest.json").write_text(json.dumps(_valid_manifest()), encoding="utf-8")

    center = AssetCenter(
        source_dir=str(source_dir),
        installed_dir=str(tmp_path / "installed"),
        build_dir=str(tmp_path / "build"),
        data_dir=str(tmp_path / "data"),
    )

    assets = center.discover()

    assert len(assets) == 1
    assert assets[0].asset_id == "system.master"
    assert center.get_asset("system.master") is not None


def test_discover_skips_manifest_missing_invocation_compliance_metadata(tmp_path) -> None:
    source_dir = tmp_path / "source"
    asset_dir = source_dir / "system.master"
    asset_dir.mkdir(parents=True)
    manifest = _valid_manifest()
    manifest["metadata"].pop("runtime_wrapper_compatibility")
    (asset_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    center = AssetCenter(
        source_dir=str(source_dir),
        installed_dir=str(tmp_path / "installed"),
        build_dir=str(tmp_path / "build"),
        data_dir=str(tmp_path / "data"),
    )

    assets = center.discover()

    assert assets == []
    assert center.get_asset("system.master") is None
