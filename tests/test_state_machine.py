import pytest

from app.models.db import Incident
from app.models.enums import IncidentStatus
from app.services.incident_service import IncidentService, InvalidTransitionError


class _DummyDB:
    def add(self, _obj):
        return None

    def flush(self):
        return None

    def commit(self):
        return None

    def refresh(self, _obj):
        return None


def test_valid_transition_path():
    service = IncidentService(_DummyDB())  # type: ignore[arg-type]
    incident = Incident(
        id="inc-1",
        service="api",
        severity="HIGH",
        status=IncidentStatus.DETECTED.value,
        scenario="api_memory_pressure",
    )
    service.transition(incident, IncidentStatus.TRIAGING)
    assert incident.status == IncidentStatus.TRIAGING.value
    service.transition(incident, IncidentStatus.INVESTIGATING)
    assert incident.status == IncidentStatus.INVESTIGATING.value


def test_invalid_transition_raises():
    service = IncidentService(_DummyDB())  # type: ignore[arg-type]
    incident = Incident(
        id="inc-2",
        service="api",
        severity="HIGH",
        status=IncidentStatus.DETECTED.value,
        scenario="api_memory_pressure",
    )
    with pytest.raises(InvalidTransitionError):
        service.transition(incident, IncidentStatus.RECOVERED)