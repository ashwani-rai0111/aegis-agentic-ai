from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    database: str
    agent_mode: str
    tool_backend: str = "mock"
    aws_configured: bool = False


class SimulateRequest(BaseModel):
    scenario: str = "api_memory_pressure"
    service: str = "production-api"
    severity: str = "HIGH"


class LiveIncidentRequest(BaseModel):
    service: str = "production-api"
    severity: str = "HIGH"


class InvestigateRequest(BaseModel):
    message: str = Field(..., min_length=3, max_length=2000)
    service: str = "signyn"
    severity: str = "HIGH"


class ObservationOut(BaseModel):
    id: str
    source: str
    name: str
    value: str
    evidence: dict[str, Any] | None = None
    timestamp: datetime

    model_config = {"from_attributes": True}


class HypothesisOut(BaseModel):
    id: str
    hypothesis: str
    evidence_for: str | None = None
    evidence_against: str | None = None
    score: float
    selected: bool

    model_config = {"from_attributes": True}


class PlanOut(BaseModel):
    id: str
    proposed_action: str
    parameters: dict[str, Any] | None = None
    risk: str
    rationale: str
    approval_required: bool
    approved: bool
    approved_by: str | None = None

    model_config = {"from_attributes": True}


class ActionOut(BaseModel):
    id: str
    tool: str
    parameters: dict[str, Any] | None = None
    approved_by: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    result: str | None = None
    success: bool

    model_config = {"from_attributes": True}


class VerificationOut(BaseModel):
    id: str
    metric: str
    before_value: str | None = None
    after_value: str | None = None
    success: bool

    model_config = {"from_attributes": True}


class AuditLogOut(BaseModel):
    id: str
    actor: str
    action: str
    details: dict[str, Any] | None = None
    timestamp: datetime
    result: str | None = None

    model_config = {"from_attributes": True}


class IncidentSummary(BaseModel):
    id: str
    service: str
    severity: str
    status: str
    summary: str | None = None
    root_cause: str | None = None
    confidence: float | None = None
    scenario: str
    agent_mode: str | None = None
    detected_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IncidentDetail(IncidentSummary):
    observations: list[ObservationOut] = Field(default_factory=list)
    hypotheses: list[HypothesisOut] = Field(default_factory=list)
    plans: list[PlanOut] = Field(default_factory=list)
    actions: list[ActionOut] = Field(default_factory=list)
    verifications: list[VerificationOut] = Field(default_factory=list)
    audit_logs: list[AuditLogOut] = Field(default_factory=list)


class ApproveRequest(BaseModel):
    approved_by: str = "human-operator"


class RejectRequest(BaseModel):
    rejected_by: str = "human-operator"
    reason: str = "Operator rejected remediation plan"


class FixRepoOut(BaseModel):
    key: str
    url: str
    profile: str
    starting_branch: str
    deploy_label: str


class FixJobCreate(BaseModel):
    repo_key: str = Field(..., min_length=1, max_length=120)
    error_text: str = Field(..., min_length=5, max_length=20000)
    notes: str | None = Field(default=None, max_length=4000)
    fix_password: str = Field(..., min_length=1, max_length=200)


class FixJobOut(BaseModel):
    id: str
    repo_key: str
    repo_url: str
    profile: str
    status: str
    error_text: str
    notes: str | None = None
    backup_branch: str | None = None
    fix_branch: str | None = None
    pr_url: str | None = None
    cursor_agent_id: str | None = None
    cursor_run_id: str | None = None
    summary: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}