import enum


class IncidentStatus(str, enum.Enum):
    DETECTED = "DETECTED"
    TRIAGING = "TRIAGING"
    INVESTIGATING = "INVESTIGATING"
    HYPOTHESIS_READY = "HYPOTHESIS_READY"
    PLAN_READY = "PLAN_READY"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    RECOVERED = "RECOVERED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"


class Severity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


ALLOWED_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.DETECTED: {IncidentStatus.TRIAGING, IncidentStatus.FAILED},
    IncidentStatus.TRIAGING: {IncidentStatus.INVESTIGATING, IncidentStatus.FAILED},
    IncidentStatus.INVESTIGATING: {
        IncidentStatus.HYPOTHESIS_READY,
        IncidentStatus.FAILED,
        IncidentStatus.ESCALATED,
    },
    IncidentStatus.HYPOTHESIS_READY: {
        IncidentStatus.PLAN_READY,
        IncidentStatus.FAILED,
        IncidentStatus.ESCALATED,
    },
    IncidentStatus.PLAN_READY: {
        IncidentStatus.AWAITING_APPROVAL,
        IncidentStatus.EXECUTING,
        IncidentStatus.ESCALATED,
        IncidentStatus.FAILED,
    },
    IncidentStatus.AWAITING_APPROVAL: {
        IncidentStatus.EXECUTING,
        IncidentStatus.ESCALATED,
        IncidentStatus.FAILED,
    },
    IncidentStatus.EXECUTING: {
        IncidentStatus.VERIFYING,
        IncidentStatus.FAILED,
        IncidentStatus.ESCALATED,
    },
    IncidentStatus.VERIFYING: {
        IncidentStatus.RECOVERED,
        IncidentStatus.FAILED,
        IncidentStatus.ESCALATED,
    },
    IncidentStatus.RECOVERED: set(),
    IncidentStatus.FAILED: set(),
    IncidentStatus.ESCALATED: set(),
}