from contextvars import ContextVar

current_incident_id: ContextVar[str | None] = ContextVar("current_incident_id", default=None)


def require_incident_id() -> str:
    incident_id = current_incident_id.get()
    if not incident_id:
        raise RuntimeError("No incident_id set in tool context")
    return incident_id