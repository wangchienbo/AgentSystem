from __future__ import annotations

from pathlib import Path

from app.orchestration.core_orchestrator import CoreOrchestrator
from app.runtime_paths import resolve_runtime_paths
from app.skills.skill_registry_service import SkillRegistryService


def test_skill_registry_service_defaults_to_resolved_installed_assets_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(tmp_path / "agentsystem-home"))
    registry = SkillRegistryService()
    assert registry._installed_dir == resolve_runtime_paths().installed_assets_dir


def test_core_orchestrator_asset_center_uses_resolved_installed_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(tmp_path / "agentsystem-home"))
    orchestrator = CoreOrchestrator()
    assert orchestrator.asset_center._installed_dir == resolve_runtime_paths().installed_assets_dir
