from __future__ import annotations

from pathlib import Path

from app.models.generated_skill import GeneratedSkillRequest
from app.services.skill_asset_service import SkillAssetService


def test_skill_asset_service_promote_archive_restore_and_consistency(tmp_path: Path) -> None:
    skill_id = "skill.api.asset"
    service = SkillAssetService(str(tmp_path / "generated_executable_skills"))

    asset, metadata = service.create_asset_scaffold(
        GeneratedSkillRequest(
            skill_id=skill_id,
            name="API Asset",
            description="asset api test",
            template_type="text_transform",
        ),
        status="candidate",
    )
    assert metadata.asset_status == "candidate"
    assert Path(asset.asset_dir).exists()

    assets = service.list_assets()
    assert any(item.skill_id == skill_id for item in assets)

    promoted = service.promote_candidate_to_core(skill_id, accepted_by="tester")
    assert promoted.asset_status == "core"
    assert promoted.accepted is True
    assert promoted.accepted_by == "tester"

    deprecated = service.deprecate_core_asset(skill_id)
    assert deprecated.asset_status == "deprecated"

    archived = service.archive_asset(skill_id, status="deprecated")
    assert archived.asset_status == "archived"

    restored = service.restore_archived_to_candidate(skill_id)
    assert restored.asset_status == "candidate"

    consistency = service.check_consistency(skill_id)
    assert consistency
    assert consistency[0].ok is True
