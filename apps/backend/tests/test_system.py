from fastapi.testclient import TestClient

from flrc.main import create_app


def test_healthz() -> None:
    response = TestClient(create_app()).get("/api/healthz")

    assert response.status_code == 204
    assert response.content == b""
