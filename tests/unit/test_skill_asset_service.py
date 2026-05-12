from __future__ import annotations

import json
from pathlib import Path

from app.models.generated_skill import GeneratedSkillRequest
from app.services.skill_asset_service import SkillAssetService


def test_skill_asset_service_creates_candidate_asset_and_index(tmp_path: Path) -> None:
    service = SkillAssetService(str(tmp_path / "data"))
    asset, metadata = service.create_asset_scaffold(
        GeneratedSkillRequest(
            skill_id="skill.test.asset",
            name="Test Asset",
            description="candidate asset",
            template_type="text_transform",
        ),
        status="candidate",
    )

    manifest = json.loads(Path(asset.manifest_path).read_text())

    assert metadata.asset_status == "candidate"
    assert Path(asset.asset_dir).exists()
    assert (Path(asset.asset_dir) / "metadata.json").exists()
    assert manifest["phase_p_invocation"]["invocation_contract_version"] == "phase-p-v1"
    assert manifest["phase_p_invocation"]["runtime_wrapper_compatibility"] is True
    index = json.loads((tmp_path / "data" / "skill_assets" / "index.json").read_text())
    assert index["assets"]
    assert index["assets"][0]["skill_id"] == "skill.test.asset"
    assert index["assets"][0]["asset_status"] == "candidate"




def test_skill_asset_service_scaffold_entrypoint_and_readme_include_phase_p_hooks(tmp_path: Path) -> None:
    service = SkillAssetService(str(tmp_path / "data"))
    asset, _metadata = service.create_asset_scaffold(
        GeneratedSkillRequest(
            skill_id="skill.test.phasep",
            name="Phase P Asset",
            description="phase p candidate",
            template_type="slugify",
        ),
        status="candidate",
    )

    entrypoint = Path(asset.entrypoint_path).read_text()
    readme = Path(asset.readme_path).read_text()
    smoke = Path(asset.asset_dir) / "tests" / "test_smoke.py"

    assert "__invocation_envelope__" in entrypoint
    assert "local_session_id" in entrypoint
    assert "Phase P runtime hook" in readme
    assert "runtime_wrapper_compatible" in smoke.read_text()
    service = SkillAssetService(str(tmp_path / "data"))
    service.create_asset_scaffold(
        GeneratedSkillRequest(
            skill_id="skill.test.promote",
            name="Promote Asset",
            description="promote candidate",
        ),
        status="candidate",
    )

    metadata = service.promote_candidate_to_core("skill.test.promote", accepted_by="tester")
    assert metadata.asset_status == "core"
    assert metadata.accepted is True
    assert metadata.accepted_by == "tester"
    core_dir = tmp_path / "data" / "skill_assets" / "core" / "executable" / "skill_test_promote"
    assert core_dir.exists()


def test_skill_asset_service_remaps_legacy_data_relative_paths_to_runtime_data_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(tmp_path / "agentsystem-home"))
    runtime_data_dir = tmp_path / "agentsystem-home" / "data"
    service = SkillAssetService(str(runtime_data_dir))
    asset, _metadata = service.create_asset_scaffold(
        GeneratedSkillRequest(
            skill_id="skill.test.legacyremap",
            name="Legacy Remap Asset",
            description="legacy remap candidate",
        ),
        status="candidate",
    )

    index_path = runtime_data_dir / "skill_assets" / "index.json"
    index = json.loads(index_path.read_text())
    index["assets"][0]["path"] = "data/skill_assets/candidates/executable/skill_test_legacyremap"
    index["assets"][0]["manifest_path"] = "data/skill_assets/candidates/executable/skill_test_legacyremap/manifest.json"
    index["assets"][0]["metadata_path"] = "data/skill_assets/candidates/executable/skill_test_legacyremap/metadata.json"
    index_path.write_text(json.dumps(index), encoding="utf-8")

    results = service.check_consistency("skill.test.legacyremap")

    assert len(results) == 1
    assert results[0].ok is True


def test_skill_asset_service_consistency_detects_missing_smoke_test(tmp_path: Path) -> None:
    service = SkillAssetService(str(tmp_path / "data"))
    asset, _metadata = service.create_asset_scaffold(
        GeneratedSkillRequest(
            skill_id="skill.test.consistency",
            name="Consistency Asset",
            description="consistency candidate",
        ),
        status="candidate",
    )
    smoke = Path(asset.asset_dir) / "tests" / "test_smoke.py"
    smoke.unlink()

    results = service.check_consistency("skill.test.consistency")
    assert len(results) == 1
    assert results[0].ok is False
    assert any(issue.kind == "missing_smoke_test" for issue in results[0].issues)
