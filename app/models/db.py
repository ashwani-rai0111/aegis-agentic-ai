from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    service: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    scenario: Mapped[str] = mapped_column(String(120), default="api_memory_pressure")
    agent_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    observations: Mapped[list[Observation]] = relationship(back_populates="incident")
    hypotheses: Mapped[list[Hypothesis]] = relationship(back_populates="incident")
    plans: Mapped[list[Plan]] = relationship(back_populates="incident")
    actions: Mapped[list[Action]] = relationship(back_populates="incident")
    verifications: Mapped[list[Verification]] = relationship(back_populates="incident")
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="incident")


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    incident: Mapped[Incident] = relationship(back_populates="observations")


class Hypothesis(Base):
    __tablename__ = "hypotheses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_for: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_against: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)

    incident: Mapped[Incident] = relationship(back_populates="hypotheses")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    proposed_action: Mapped[str] = mapped_column(String(160), nullable=False)
    parameters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    risk: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)

    incident: Mapped[Incident] = relationship(back_populates="plans")


class Action(Base):
    __tablename__ = "actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    tool: Mapped[str] = mapped_column(String(160), nullable=False)
    parameters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)

    incident: Mapped[Incident] = relationship(back_populates="actions")


class Verification(Base):
    __tablename__ = "verifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    metric: Mapped[str] = mapped_column(String(160), nullable=False)
    before_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)

    incident: Mapped[Incident] = relationship(back_populates="verifications")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str | None] = mapped_column(
        ForeignKey("incidents.id"), nullable=True, index=True
    )
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(160), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # kept for schema compatibility with the product plan
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)

    incident: Mapped[Incident | None] = relationship(back_populates="audit_logs")