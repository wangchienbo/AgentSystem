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

    assert metadata.asset_status == "candidate"
    assert Path(asset.asset_dir).exists()
    assert (Path(asset.asset_dir) / "metadata.json").exists()
    index = json.loads((tmp_path / "data" / "skill_assets" / "index.json").read_text())
    assert index["assets"]
    assert index["assets"][0]["skill_id"] == "skill.test.asset"
    assert index["assets"][0]["asset_status"] == "candidate"


def test_skill_asset_service_promotes_candidate_to_core(tmp_path: Path) -> None:
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
