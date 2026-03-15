from fastapi.testclient import TestClient

from app.api.main import app


client = TestClient(app)


def test_blueprint_validation_missing_fields() -> None:
    payload = {
        "id": "bp_001",
        "name": "Test Blueprint",
        "goal": "Create an app",
        "roles": [],
        "tasks": [],
        "workflows": [],
        "views": [],
        "required_modules": [],
        "required_skills": []
    }
    response = client.post("/blueprints/validate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert "roles" in data["missing"]
    assert "workflows" in data["missing"]
    assert "required_modules" in data["missing"]
