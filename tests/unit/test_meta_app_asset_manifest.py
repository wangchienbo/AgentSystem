from __future__ import annotations

import json
from pathlib import Path

from app.models.app_blueprint import AppBlueprint
from app.orchestration.meta_app.orchestrator import MetaAppCreationOrchestrator
from app.services.meta_app.bootstrap import MetaAppBootstrapService
from app.services.skill_factory import SkillFactoryService


class _DummySkillFactory(SkillFactoryService):
    def __init__(self) -> None:  # pragma: no cover
        pass


def _build_blueprint() -> AppBlueprint:
    return AppBlueprint(
        id="bp.meta.asset",
        name="Meta Asset App",
        goal="verify meta app source materialization",
        roles=[],
        tasks=[],
        workflows=[{"id": "wf.meta", "name": "meta", "triggers": ["manual"], "steps": []}],
        required_modules=["state.get"],
        required_skills=["skill.task-list-executor"],
        runtime_policy={
            "execution_mode": "service",
            "activation": "on_demand",
            "restart_policy": "on_failure",
            "persistence_level": "standard",
            "idle_strategy": "suspend",
        },
    )


def test_meta_app_write_to_source_uses_asset_manifest_standard(tmp_path: Path) -> None:
    orchestrator = MetaAppCreationOrchestrator(
        meta_app_bootstrap=MetaAppBootstrapService(),
        skill_factory=_DummySkillFactory(),
        source_dir=str(tmp_path / "source"),
    )

    blueprint = _build_blueprint()
    orchestrator._write_to_source(blueprint, "app.meta.asset")

    manifest_path = tmp_path / "source" / "app.meta.asset" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["asset_id"] == "app.meta.asset"
    assert manifest["asset_type"] == "app"
    assert manifest["entry"] == "blueprint.json"
    assert manifest["owner"] == "system"
    assert manifest["owner_role"] == "admin"
    assert manifest["source_path"] == "source/app.meta.asset"
    assert manifest["metadata"]["blueprint_id"] == blueprint.id
    assert manifest["metadata"]["required_skills"] == ["skill.task-list-executor"]
