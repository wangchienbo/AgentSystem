from __future__ import annotations

from pathlib import Path
import shutil

from fastapi.testclient import TestClient

from app.api.main import app
from app.services.skill_asset_service import SkillAssetService

client = TestClient(app)


def test_skill_asset_api_promote_archive_restore_and_consistency() -> None:
    skill_id = "skill.api.asset"
    asset_service = SkillAssetService("data/namespaces/generated_executable_skills")
    for status in ["candidate", "core", "deprecated", "archived"]:
        path = asset_service.resolve_asset_dir(skill_id, status=status)
        if path.exists():
            shutil.rmtree(path)
    asset_service.rebuild_index()

    materialize = client.post(
        "/skills/create",
        json={
            "skill_id": skill_id,
            "name": "API Asset",
            "description": "asset api test",
            "adapter_kind": "executable",
            "generation_operation": "text_transform",
            "tags": ["asset-api"],
            "smoke_test_inputs": {"text": "hello"},
            "schemas": {
                "input": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False},
                "output": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False},
                "error": {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"], "additionalProperties": True},
            },
        },
    )
    assert materialize.status_code == 200

    assets = client.get("/skill-assets").json()
    assert any(item["skill_id"] == skill_id for item in assets)

    promote = client.post(f"/skill-assets/{skill_id}/promote", json={"accepted_by": "tester"})
    assert promote.status_code == 200
    assert promote.json()["asset_status"] == "core"

    deprecate = client.post(f"/skill-assets/{skill_id}/deprecate")
    assert deprecate.status_code == 200
    assert deprecate.json()["asset_status"] == "deprecated"

    archive = client.post(f"/skill-assets/{skill_id}/archive", json={"status": "deprecated"})
    assert archive.status_code == 200
    assert archive.json()["asset_status"] == "archived"

    restore = client.post(f"/skill-assets/{skill_id}/restore")
    assert restore.status_code == 200
    assert restore.json()["asset_status"] == "candidate"

    consistency = client.get(f"/skill-assets/{skill_id}/consistency")
    assert consistency.status_code == 200
    assert consistency.json()
