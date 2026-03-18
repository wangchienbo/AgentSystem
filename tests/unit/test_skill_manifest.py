from fastapi.testclient import TestClient

from app.api.main import app


client = TestClient(app)


def test_registered_system_skills_expose_minimal_manifests() -> None:
    response = client.get("/skills")
    assert response.status_code == 200
    skills = {item["skill_id"]: item for item in response.json()}

    assert skills["system.app_config"]["manifest"]["runtime_adapter"] == "callable"
    assert skills["system.state"]["manifest"]["tags"] == ["system", "state"]
    assert skills["system.audit"]["manifest"]["description"]
    assert skills["system.context"]["manifest"]["skill_id"] == "system.context"
