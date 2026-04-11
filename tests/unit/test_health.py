from pathlib import Path

from tests.unit.api_test_helper import create_isolated_test_client



def test_health(tmp_path: Path) -> None:
    client = create_isolated_test_client(tmp_path)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_version(tmp_path: Path) -> None:
    client = create_isolated_test_client(tmp_path)
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json()["version"] == "0.1.0"
