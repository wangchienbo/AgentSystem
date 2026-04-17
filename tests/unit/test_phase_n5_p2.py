"""Tests for Phase N.5 P2 features."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from app.system.catalog.asset_center import AssetCenter


@pytest.fixture
def asset_center(tmp_path):
    """Create an AssetCenter with test assets including dependencies."""
    src = tmp_path / "source"
    build = tmp_path / "build"
    installed = tmp_path / "installed"
    data = tmp_path / "data"

    # Shared dependency skill
    (src / "shared.logging").mkdir(parents=True)
    (src / "shared.logging" / "manifest.json").write_text(json.dumps({
        "asset_id": "shared.logging",
        "asset_type": "skill",
        "name": "Shared Logging",
        "version": "0.1.0",
        "entry": "skill.py",
        "owner": "system.master",
        "owner_role": "system",
        "dependencies": [],
        "source_path": "source/shared.logging",
        "description": "Shared logging",
        "metadata": {},
    }))
    (src / "shared.logging" / "skill.py").write_text("# logging skill")

    # App that depends on shared.logging
    (src / "test.app").mkdir(parents=True)
    (src / "test.app" / "manifest.json").write_text(json.dumps({
        "asset_id": "test.app",
        "asset_type": "app",
        "name": "Test App",
        "version": "0.2.0",
        "entry": "main.py",
        "owner": "system.master",
        "owner_role": "system",
        "dependencies": ["shared.logging"],
        "source_path": "source/test.app",
        "description": "Test app",
        "metadata": {},
    }))
    (src / "test.app" / "main.py").write_text("# main")

    ac = AssetCenter(
        source_dir=str(src),
        installed_dir=str(installed),
        build_dir=str(build),
        data_dir=str(data),
    )
    ac.discover()
    return ac


def test_build_resolves_dependencies(asset_center):
    """N5-02: Building an asset resolves and copies its dependencies."""
    record = asset_center.build("test.app")
    assert record.asset_id == "test.app"

    build_output = asset_center._build_dir / "test.app" / record.build_hash
    deps_dir = build_output / "deps"

    assert (deps_dir / "shared.logging").exists()
    assert (deps_dir / "shared.logging" / "skill.py").exists()


def test_build_no_dependencies(asset_center):
    """Building an asset with no dependencies should not create deps dir."""
    record = asset_center.build("shared.logging")
    build_output = asset_center._build_dir / "shared.logging" / record.build_hash
    deps_dir = build_output / "deps"
    assert not deps_dir.exists()


def test_build_version_isolation(asset_center):
    """N5-03: Different versions produce different build hashes."""
    record1 = asset_center.build("test.app")
    
    # Update version to simulate a new release
    asset = asset_center._registry["test.app"]
    asset.version = "0.3.0"
    record2 = asset_center.build("test.app")

    # Different versions → different build hashes
    assert record1.build_hash != record2.build_hash
    dir1 = asset_center._build_dir / "test.app" / record1.build_hash
    dir2 = asset_center._build_dir / "test.app" / record2.build_hash
    assert dir1.exists()
    assert dir2.exists()
