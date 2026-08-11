from app.tools.backend import MockBackend, get_tool_backend, resolve_tool_backend_name
from app.tools.mock_state import mock_infra


def test_simulate_incident_uses_mock_backend():
    incident_id = "test-incident-mock-backend"
    mock_infra.bootstrap(incident_id, scenario="api_memory_pressure")
    assert resolve_tool_backend_name(incident_id) == "mock"
    backend = get_tool_backend(incident_id)
    assert isinstance(backend, MockBackend)
    snap = backend.snapshot()
    assert snap["alarm"]["state"] == "ALARM"
    assert "api" in [p["name"] for p in snap["pm2"]["processes"]]
