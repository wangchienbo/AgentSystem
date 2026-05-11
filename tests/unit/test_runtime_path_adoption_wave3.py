from __future__ import annotations

from app.persistence.path_store import PathStore
from app.runtime_paths import resolve_runtime_paths
from app.skills.generated_callable_materializer import GeneratedCallableMaterializer
from app.skills.skill_config_center import SkillConfigCenter


def test_generated_callable_materializer_defaults_to_resolved_data_dir(monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", "/tmp/agentsystem-home")
    materializer = GeneratedCallableMaterializer()
    assert materializer._base_path == resolve_runtime_paths().data_dir / "generated_callable_skills"


def test_skill_config_center_defaults_to_resolved_data_dir(monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", "/tmp/agentsystem-home")
    center = SkillConfigCenter()
    assert center._config_file == resolve_runtime_paths().data_dir / "skill_config" / "registry.yaml"


def test_path_store_defaults_to_resolved_data_dir(monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", "/tmp/agentsystem-home")
    store = PathStore()
    assert store._paths_dir == resolve_runtime_paths().data_dir / "paths"
