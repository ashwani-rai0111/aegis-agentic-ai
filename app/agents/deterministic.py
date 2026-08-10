"""Deterministic agent loop for local demos/tests without an LLM API key.

Mirrors the full CrewAI workflow:
observe → investigate (metrics/processes/mysql/pm2/logs) → RCA → plan →
safety → act → verify → recover/escalate.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.enums import IncidentStatus
from app.policies.safety import evaluate_action
from app.services.incident_service import IncidentService
from app.services.remediation import execute_approved_plan
from app.tools.context import current_incident_id
from app.tools.mock_state import SCENARIO_MYSQL_RESTART_REQUIRED, mock_infra
from app.tools.ops_tools import (
    GetCloudWatchAlarmTool,
    GetEc2StatusTool,
    GetMysqlStatusTool,
    GetNginxStatusTool,
    GetPm2LogsTool,
    GetPm2StatusTool,
    GetProcessMemoryTool,
    GetSystemMetricsTool,
    HealthCheckTool,
    QueryLogsTool,
)


def run_deterministic_incident(db: Session, incident_id: str) -> dict[str, Any]:
    service = IncidentService(db)
    incident = service.get(incident_id)
    if not incident:
        raise ValueError(f"Incident not found: {incident_id}")

    token = current_incident_id.set(incident_id)
    try:
        # 1) Incident manager / monitoring
        service.transition(incident, IncidentStatus.TRIAGING)
        alarm = json.loads(
            GetCloudWatchAlarmTool()._run(alarm_name=mock_infra.get(incident_id)["alarm"]["alarm_name"])
        )
        service.add_observation(
            incident_id,
            source="cloudwatch",
            name="alarm",
            value=alarm["state"],
            evidence=alarm,
        )

        # 2) Investigate with tools — decide next step from current state
        service.transition(incident, IncidentStatus.INVESTIGATING)
        metrics = json.loads(GetSystemMetricsTool()._run())
        processes = json.loads(GetProcessMemoryTool()._run())
        mysql = json.loads(GetMysqlStatusTool()._run())
        nginx = json.loads(GetNginxStatusTool()._run())
        ec2 = json.loads(GetEc2StatusTool()._run())
        pm2 = json.loads(GetPm2StatusTool()._run())
        pm2_logs = json.loads(GetPm2LogsTool()._run(process_name="api"))
        logs = json.loads(
            QueryLogsTool()._run(service=incident.service, time_range_minutes=30)
        )
        health = json.loads(HealthCheckTool()._run())

        for source, name, value, evidence in [
            ("system", "metrics", json.dumps(metrics["metrics"]), metrics),
            ("host", "top_processes", json.dumps(processes["processes"]), processes),
            ("mysql", "status", json.dumps(mysql["mysql"]), mysql),
            ("nginx", "status", json.dumps(nginx["nginx"]), nginx),
            ("ec2", "status", json.dumps(ec2["ec2"]), ec2),
            ("pm2", "process_status", json.dumps(pm2["processes"]), pm2),
            ("pm2", "api_logs", "\n".join(pm2_logs["lines"]), pm2_logs),
            ("logs", "recent_errors", "\n".join(logs["lines"]), logs),
            ("http", "health_check", str(health["health"]["http_status"]), health),
        ]:
            service.add_observation(
                incident_id,
                source=source,
                name=name,
                value=value if isinstance(value, str) else str(value),
                evidence=evidence,
            )

        # 3) Differential diagnosis from tool results
        service.transition(incident, IncidentStatus.HYPOTHESIS_READY)
        mysql_healthy = bool(mysql["mysql"].get("healthy", True))
        api_proc = next((p for p in pm2["processes"] if p["name"] == "api"), None)
        top_proc = (processes["processes"] or [{}])[0]
        memory = float(metrics["metrics"]["memory_utilization"])

        if incident.scenario == SCENARIO_MYSQL_RESTART_REQUIRED or not mysql_healthy:
            hypotheses = [
                {
                    "hypothesis": "MySQL connection/thread pileup saturating the database",
                    "evidence_for": (
                        f"mysql healthy={mysql_healthy}, "
                        f"connections={mysql['mysql'].get('current_connections')}/"
                        f"{mysql['mysql'].get('max_connections')}, "
                        f"threads_running={mysql['mysql'].get('threads_running')}"
                    ),
                    "evidence_against": "PM2 api process itself is not marked unhealthy",
                    "score": 0.9,
                    "selected": True,
                },
                {
                    "hypothesis": "Node API memory leak",
                    "evidence_for": f"host memory={memory}%",
                    "evidence_against": "PM2 api looks healthy; DB errors dominate logs",
                    "score": 0.25,
                    "selected": False,
                },
            ]
            proposed_action = "restart_mysql"
            parameters: dict[str, Any] = {}
            rationale = (
                "MySQL is unhealthy with connection/thread saturation. "
                "Restarting MySQL is the lowest-risk medium remediation after ruling out "
                "an unhealthy Node process. Requires human approval."
            )
        else:
            # Classic path: MySQL looks large but is normal; Node/api is unhealthy
            hypotheses = [
                {
                    "hypothesis": (
                        "Unhealthy Node API (PM2 api / node-server) leaking memory under load"
                    ),
                    "evidence_for": (
                        f"memory={memory}%, swap={metrics['metrics']['swap_utilization']}%, "
                        f"top_process={top_proc.get('name')} {top_proc.get('memory_mb')}MB, "
                        f"PM2 api restarts={api_proc.get('restarts') if api_proc else '?'}, "
                        f"unhealthy={api_proc.get('unhealthy') if api_proc else '?'}"
                    ),
                    "evidence_against": (
                        "MySQL connections are modest and buffer pool looks normal"
                    ),
                    "score": 0.88,
                    "selected": True,
                },
                {
                    "hypothesis": "MySQL is the primary memory consumer / root cause",
                    "evidence_for": (
                        f"mysqld memory_mb in process list; "
                        f"buffer_pool={mysql['mysql'].get('buffer_pool_mb')}MB"
                    ),
                    "evidence_against": (
                        f"MySQL healthy={mysql_healthy}, "
                        f"current_connections={mysql['mysql'].get('current_connections')}"
                    ),
                    "score": 0.28,
                    "selected": False,
                },
                {
                    "hypothesis": "EC2 / nginx failure",
                    "evidence_for": "HTTP health degraded",
                    "evidence_against": (
                        f"ec2={ec2['ec2'].get('state')}, nginx={nginx['nginx'].get('status')}"
                    ),
                    "score": 0.1,
                    "selected": False,
                },
            ]
            proposed_action = "restart_pm2_process"
            parameters = {"process_name": "api"}
            rationale = (
                "Differential diagnosis ruled out MySQL (healthy connections/buffer pool). "
                "Node-server/PM2 api is unhealthy with high memory and restart count. "
                "restart_pm2_process(api) is low-risk and allowlisted for auto execution."
            )

        selected = next(h for h in hypotheses if h["selected"])
        for item in hypotheses:
            service.add_hypothesis(incident_id, **item)

        incident.root_cause = selected["hypothesis"]
        incident.confidence = selected["score"]
        db.commit()

        # 4) Plan + safety
        service.transition(incident, IncidentStatus.PLAN_READY)
        decision = evaluate_action(
            proposed_action,
            parameters,
            already_approved=False,
            actions_already_taken=service.count_actions(incident_id),
        )
        service.add_plan(
            incident_id,
            proposed_action=proposed_action,
            parameters=parameters,
            risk=decision.risk.value,
            rationale=rationale,
            approval_required=decision.approval_required,
            approved=decision.allowed and not decision.approval_required,
            approved_by="policy-auto" if decision.allowed and not decision.approval_required else None,
        )

        # 5) Execute / await approval / escalate + verify
        return execute_approved_plan(
            db,
            incident_id,
            already_approved=False,
            summary=(
                "Deterministic agents observed the alarm, gathered host/process/MySQL/PM2 "
                "evidence, selected root cause via differential diagnosis, applied policy, "
                "executed remediation when allowed, and verified recovery."
            ),
        )
    finally:
        current_incident_id.reset(token)


def resume_deterministic_incident(db: Session, incident_id: str) -> dict[str, Any]:
    """Continue after human approval."""
    return execute_approved_plan(db, incident_id, already_approved=True)
