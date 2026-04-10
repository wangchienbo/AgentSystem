from pathlib import Path

from tests.unit.api_test_helper import create_isolated_test_client


def test_registered_system_skills_expose_minimal_manifests(tmp_path: Path) -> None:
    client = create_isolated_test_client(tmp_path)
    response = client.get("/skills")
    assert response.status_code == 200
    skills = {item["skill_id"]: item for item in response.json()}

    assert skills["system.app_config"]["manifest"]["runtime_adapter"] == "callable"
    assert skills["system.app_config"]["manifest"]["adapter"]["kind"] == "callable"
    assert skills["system.state"]["manifest"]["tags"] == ["system", "state"]
    assert skills["system.audit"]["manifest"]["description"]
    assert skills["system.context"]["manifest"]["skill_id"] == "system.context"
