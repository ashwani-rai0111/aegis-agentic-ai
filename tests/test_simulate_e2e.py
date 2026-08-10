import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    # Force deterministic agents for reliable local/CI runs.
    os.environ["AEGIS_AGENT_MODE"] = "deterministic"
    from app.config import get_settings
    from app.database.session import check_db

    get_settings.cache_clear()
    if not check_db():
        pytest.skip("Postgres is not available on DATABASE_URL")

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["database"] == "up"
    assert body["agent_mode"] == "deterministic"


def test_simulate_recovers(client: TestClient):
    response = client.post(
        "/incidents/simulate",
        json={
            "scenario": "api_memory_pressure",
            "service": "production-api",
            "severity": "HIGH",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "RECOVERED"
    assert body["root_cause"]
    assert len(body["observations"]) >= 3
    assert len(body["hypotheses"]) >= 1
    assert len(body["plans"]) == 1
    assert len(body["actions"]) == 1
    assert body["actions"][0]["success"] is True
    assert len(body["verifications"]) >= 2
    assert all(v["success"] for v in body["verifications"])

    detail = client.get(f"/incidents/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "RECOVERED"