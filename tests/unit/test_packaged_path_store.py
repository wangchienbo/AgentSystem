from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.persistence.path_store import PathStore, PathStoreError, PathTemplate


def test_non_packaged_path_store_reports_mutable_state(tmp_path: Path) -> None:
    paths_dir = tmp_path / "paths"
    paths_dir.mkdir(parents=True)
    store = PathStore(paths_dir=str(paths_dir))

    assert store.bundle_manifest() is None
    assert store.is_packaged_bundle is False
    paths_dir = tmp_path / "builtin_paths"
    paths_dir.mkdir(parents=True)
    (paths_dir / "builtin_paths_manifest.json").write_text(
        json.dumps({"asset_id": "builtin.control_plane.paths"}),
        encoding="utf-8",
    )
    store = PathStore(paths_dir=str(paths_dir))

    assert store.bundle_manifest() == {"asset_id": "builtin.control_plane.paths"}
    assert store.is_packaged_bundle is True
    with pytest.raises(PathStoreError, match="read-only"):
        store.save(PathTemplate(path_id="demo.path", name="Demo Path"))


def test_packaged_builtin_path_store_is_read_only_for_remove(tmp_path: Path) -> None:
    paths_dir = tmp_path / "builtin_paths"
    paths_dir.mkdir(parents=True)
    (paths_dir / "builtin_paths_manifest.json").write_text(
        json.dumps({"asset_id": "builtin.control_plane.paths"}),
        encoding="utf-8",
    )
    (paths_dir / "demo_path.yaml").write_text("path_id: demo.path\nsteps: []\n", encoding="utf-8")
    store = PathStore(paths_dir=str(paths_dir))
    store.load_all()

    with pytest.raises(PathStoreError, match="read-only"):
        store.remove("demo.path")
