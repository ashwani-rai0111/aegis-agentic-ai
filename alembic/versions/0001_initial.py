"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("service", sa.String(length=120), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=48), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("root_cause", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("scenario", sa.String(length=120), nullable=False),
        sa.Column("agent_mode", sa.String(length=32), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_incidents_status", "incidents", ["status"])

    op.create_table(
        "observations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("incident_id", sa.String(length=36), sa.ForeignKey("incidents.id")),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_observations_incident_id", "observations", ["incident_id"])

    op.create_table(
        "hypotheses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("incident_id", sa.String(length=36), sa.ForeignKey("incidents.id")),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("evidence_for", sa.Text(), nullable=True),
        sa.Column("evidence_against", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_hypotheses_incident_id", "hypotheses", ["incident_id"])

    op.create_table(
        "plans",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("incident_id", sa.String(length=36), sa.ForeignKey("incidents.id")),
        sa.Column("proposed_action", sa.String(length=160), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=True),
        sa.Column("risk", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("approved_by", sa.String(length=120), nullable=True),
    )
    op.create_index("ix_plans_incident_id", "plans", ["incident_id"])

    op.create_table(
        "actions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("incident_id", sa.String(length=36), sa.ForeignKey("incidents.id")),
        sa.Column("tool", sa.String(length=160), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=True),
        sa.Column("approved_by", sa.String(length=120), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_actions_incident_id", "actions", ["incident_id"])

    op.create_table(
        "verifications",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("incident_id", sa.String(length=36), sa.ForeignKey("incidents.id")),
        sa.Column("metric", sa.String(length=160), nullable=False),
        sa.Column("before_value", sa.Text(), nullable=True),
        sa.Column("after_value", sa.Text(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_verifications_incident_id", "verifications", ["incident_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("incident_id", sa.String(length=36), sa.ForeignKey("incidents.id"), nullable=True),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=160), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
    )
    op.create_index("ix_audit_logs_incident_id", "audit_logs", ["incident_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("verifications")
    op.drop_table("actions")
    op.drop_table("plans")
    op.drop_table("hypotheses")
    op.drop_table("observations")
    op.drop_table("incidents")