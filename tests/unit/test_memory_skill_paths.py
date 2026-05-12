from __future__ import annotations

from app.runtime_paths import resolve_runtime_paths
from app.skills.system_skills.memory import MemorySkillService


def test_memory_skill_service_defaults_to_install_model_data_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(tmp_path / "agentsystem-home"))

    service = MemorySkillService()

    assert service._memory_dir == resolve_runtime_paths().data_dir / "memory" / "users"
