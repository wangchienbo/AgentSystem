from __future__ import annotations

import json
from pathlib import Path

from app.bootstrap.runtime import materialize_builtin_path_definitions
from app.runtime_paths import resolve_runtime_paths


def test_materialize_builtin_path_definitions_projects_repo_paths_into_installed_assets(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    source_paths = repo_root / "data" / "paths"
    source_paths.mkdir(parents=True)
    (source_paths / "query_help.yaml").write_text("path_id: query_help\nsteps: []\n", encoding="utf-8")
    (source_paths / "greet.yaml").write_text("path_id: greet\nsteps: []\n", encoding="utf-8")
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(tmp_path / "agentsystem-home"))

    destination = materialize_builtin_path_definitions(repo_root)
    runtime_paths = resolve_runtime_paths(repo_root)

    assert destination == runtime_paths.installed_assets_dir / "builtin_paths"
    assert (destination / "query_help.yaml").exists()
    assert (destination / "greet.yaml").exists()
    manifest = json.loads((destination / "builtin_paths_manifest.json").read_text(encoding="utf-8"))
    assert manifest["asset_id"] == "builtin.control_plane.paths"
    assert manifest["asset_type"] == "path"
    assert manifest["projected_files"] == ["greet.yaml", "query_help.yaml"]
    assert [entry["name"] for entry in manifest["projected_entries"]] == ["greet.yaml", "query_help.yaml"]
    assert all(len(entry["sha256"]) == 64 for entry in manifest["projected_entries"])


def test_materialize_builtin_path_definitions_removes_stale_projected_yaml(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    source_paths = repo_root / "data" / "paths"
    source_paths.mkdir(parents=True)
    (source_paths / "query_help.yaml").write_text("path_id: query_help\nsteps: []\n", encoding="utf-8")
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(tmp_path / "agentsystem-home"))
    destination = resolve_runtime_paths(repo_root).installed_assets_dir / "builtin_paths"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "stale.yaml").write_text("path_id: stale\nsteps: []\n", encoding="utf-8")

    materialize_builtin_path_definitions(repo_root)

    assert (destination / "query_help.yaml").exists()
    assert not (destination / "stale.yaml").exists()
