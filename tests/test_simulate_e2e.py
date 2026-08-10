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


def test_simulate_api_memory_pressure_recovers(client: TestClient):
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
    assert len(body["hypotheses"]) >= 2
    assert len(body["plans"]) == 1
    assert body["plans"][0]["proposed_action"] == "restart_pm2_process"
    assert len(body["actions"]) == 1
    assert body["actions"][0]["success"] is True
    assert len(body["verifications"]) >= 2
    assert all(v["success"] for v in body["verifications"])

    detail = client.get(f"/incidents/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "RECOVERED"


def test_mysql_scenario_awaits_approval_then_recovers(client: TestClient):
    response = client.post(
        "/incidents/simulate",
        json={
            "scenario": "mysql_restart_required",
            "service": "production-api",
            "severity": "CRITICAL",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "AWAITING_APPROVAL"
    assert body["plans"][0]["proposed_action"] == "restart_mysql"
    assert body["plans"][0]["approval_required"] is True
    assert body["actions"] == []

    approved = client.post(
        f"/incidents/{body['id']}/approve",
        json={"approved_by": "pytest-operator"},
    )
    assert approved.status_code == 200, approved.text
    after = approved.json()
    assert after["status"] == "RECOVERED"
    assert len(after["actions"]) == 1
    assert after["actions"][0]["tool"] == "restart_mysql"
    assert after["actions"][0]["success"] is True
    assert len(after["verifications"]) >= 2


def test_reject_escalates(client: TestClient):
    response = client.post(
        "/incidents/simulate",
        json={
            "scenario": "mysql_restart_required",
            "service": "production-api",
            "severity": "HIGH",
        },
    )
    assert response.status_code == 200
    incident_id = response.json()["id"]
    assert response.json()["status"] == "AWAITING_APPROVAL"

    rejected = client.post(
        f"/incidents/{incident_id}/reject",
        json={"rejected_by": "pytest-operator", "reason": "Not safe right now"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "ESCALATED"
    assert rejected.json()["actions"] == []
