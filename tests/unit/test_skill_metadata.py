from fastapi.testclient import TestClient

from app.api.main import app


client = TestClient(app)


def test_system_skills_expose_capability_profiles_via_api() -> None:
    response = client.get("/skills")
    assert response.status_code == 200
    skills = {item["skill_id"]: item for item in response.json()}

    assert skills["system.app_config"]["capability_profile"]["runtime_criticality"] == "C2_required_runtime"
    assert skills["system.state"]["capability_profile"]["execution_locality"] == "local"
    assert skills["system.audit"]["capability_profile"]["invocation_default"] == "automatic"
    assert skills["system.context"]["capability_profile"]["network_requirement"] == "N0_none"
    assert skills["skill.echo"]["runtime_adapter"] == "callable"
