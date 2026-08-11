"""Deterministic agent loop for local demos/tests without an LLM API key.

Mirrors the full CrewAI workflow:
observe → investigate (metrics/processes/mysql/pm2/logs) → RCA → plan →
safety → act → verify → recover/escalate.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.agents.confidence import normalize_confidence
from app.agents.issue_focus import mentions_database, summarize_mysql_for_question
from app.agents.pm2_targets import is_pm2_unhealthy, pick_pm2_restart_target
from app.config import get_settings
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


def run_deterministic_incident(
    db: Session,
    incident_id: str,
    *,
    user_message: str | None = None,
) -> dict[str, Any]:
    service = IncidentService(db)
    incident = service.get(incident_id)
    if not incident:
        raise ValueError(f"Incident not found: {incident_id}")

    settings = get_settings()
    report = (user_message or incident.summary or "").strip()
    token = current_incident_id.set(incident_id)
    try:
        # 1) Incident manager / monitoring
        service.transition(incident, IncidentStatus.TRIAGING)
        if mock_infra.has(incident_id):
            alarm_name = mock_infra.get(incident_id)["alarm"]["alarm_name"]
        else:
            alarm_name = settings.aegis_cw_alarm_name or "unknown"
        alarm = json.loads(GetCloudWatchAlarmTool()._run(alarm_name=alarm_name))
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
        log_targets = ["websites", "node-server", "api"]
        pm2_log_bundles: dict[str, Any] = {}
        for proc_name in log_targets:
            if any(p.get("name") == proc_name for p in pm2.get("processes") or []):
                pm2_log_bundles[proc_name] = json.loads(
                    GetPm2LogsTool()._run(process_name=proc_name)
                )
        if not pm2_log_bundles:
            pm2_log_bundles["api"] = json.loads(
                GetPm2LogsTool()._run(process_name="api")
            )
        logs = json.loads(
            QueryLogsTool()._run(service=incident.service, time_range_minutes=30)
        )
        health = json.loads(HealthCheckTool()._run())

        observations = [
            ("system", "metrics", json.dumps(metrics["metrics"]), metrics),
            ("host", "top_processes", json.dumps(processes["processes"]), processes),
            ("mysql", "status", json.dumps(mysql["mysql"]), mysql),
            ("nginx", "status", json.dumps(nginx["nginx"]), nginx),
            ("ec2", "status", json.dumps(ec2["ec2"]), ec2),
            ("pm2", "process_status", json.dumps(pm2["processes"]), pm2),
            ("logs", "recent_errors", "\n".join(logs["lines"]), logs),
            ("http", "health_check", str(health["health"]["http_status"]), health),
        ]
        if report:
            observations.insert(
                0,
                ("user", "reported_issue", report, {"message": report}),
            )
        for proc_name, bundle in pm2_log_bundles.items():
            observations.append(
                (
                    "pm2",
                    f"{proc_name}_logs",
                    "\n".join(bundle.get("lines") or []),
                    bundle,
                )
            )
        for source, name, value, evidence in observations:
            service.add_observation(
                incident_id,
                source=source,
                name=name,
                value=value if isinstance(value, str) else str(value),
                evidence=evidence,
            )

        # 3) Differential diagnosis from live tool results (not memorized answers)
        service.transition(incident, IncidentStatus.HYPOTHESIS_READY)
        mysql_healthy = bool(mysql["mysql"].get("healthy", True))
        top_proc = (processes["processes"] or [{}])[0]
        memory = float(metrics["metrics"].get("memory_utilization") or 0)
        http_status = int(health.get("health", {}).get("http_status") or 0)
        health_ok = bool(health.get("health", {}).get("ok"))
        if "ok" not in (health.get("health") or {}):
            health_ok = 200 <= http_status < 400
        health_bad = not health_ok and http_status != 0
        if http_status == 0 and not settings.aegis_healthcheck_url:
            health_bad = False
            health_ok = True

        allowlist = settings.pm2_allowlist()
        pm2_procs = pm2.get("processes") or []
        any_pm2_unhealthy = any(
            p.get("name") in allowlist and is_pm2_unhealthy(p) for p in pm2_procs
        )
        pm2_target = pick_pm2_restart_target(
            pm2_procs,
            user_message=report,
            allowlist=allowlist,
            only_if_unhealthy=True,
        )

        mysql_block = mysql.get("mysql") or {}
        mysql_severe = bool(mysql_block.get("severe"))
        mentions_db = mentions_database(report)
        mysql_summary = summarize_mysql_for_question(mysql_block, report)
        # Prefer MySQL remediation when DB is clearly bad; otherwise app/PM2 first.
        prefer_mysql = incident.scenario == SCENARIO_MYSQL_RESTART_REQUIRED or (
            not mysql_healthy
            and (
                mysql_severe
                or mentions_db
                or not (health_bad or any_pm2_unhealthy)
            )
        )

        if mentions_db and mysql_summary["healthy"]:
            hypotheses = [
                {
                    "hypothesis": mysql_summary["root_cause"],
                    "evidence_for": mysql_summary["detail"],
                    "evidence_against": "n/a",
                    "score": 0.92,
                    "selected": True,
                }
            ]
            proposed_action = ""
            parameters = {}
            rationale = "Live MySQL probes passed for the asked database(s)."
            outcome_mode = "healthy"
        elif prefer_mysql:
            hypotheses = [
                {
                    "hypothesis": "MySQL connection/thread pileup saturating the database",
                    "evidence_for": (
                        f"mysql healthy={mysql_healthy}, severe={mysql_severe}, "
                        f"connections={mysql_block.get('current_connections')}/"
                        f"{mysql_block.get('max_connections')}, "
                        f"threads_running={mysql_block.get('threads_running')}, "
                        f"production={mysql_block.get('production')}, "
                        f"staging={mysql_block.get('staging')}, "
                        f"reasons={mysql_block.get('reasons')}"
                    ),
                    "evidence_against": "PM2 app processes may still be online",
                    "score": 0.9,
                    "selected": True,
                },
                {
                    "hypothesis": "Node/website process issue",
                    "evidence_for": f"host memory={memory}%",
                    "evidence_against": "DB errors dominate evidence",
                    "score": 0.25,
                    "selected": False,
                },
            ]
            proposed_action = "restart_mysql"
            parameters: dict[str, Any] = {}
            rationale = (
                "MySQL production/staging checks indicate a database problem. "
                "Restarting MySQL requires human approval."
            )
            outcome_mode = "remediate"
        elif not health_bad and not any_pm2_unhealthy and mysql_healthy:
            endpoint = (
                health.get("health", {}).get("endpoint")
                or settings.aegis_healthcheck_url
            )
            hypotheses = [
                {
                    "hypothesis": (
                        f"Website/service appears healthy "
                        f"(HTTP {http_status} from {endpoint}; PM2 allowlisted apps online; "
                        f"MySQL ok)"
                    ),
                    "evidence_for": (
                        f"user_report={report[:200]!r}, http={http_status}, "
                        f"health_ok={health_ok}, alarm={alarm.get('state')}, "
                        f"pm2={[{'name': p.get('name'), 'status': p.get('status')} for p in pm2_procs]}, "
                        f"mysql={mysql_summary['detail']}"
                    ),
                    "evidence_against": "n/a",
                    "score": 0.9,
                    "selected": True,
                }
            ]
            proposed_action = ""
            parameters = {}
            rationale = "Live checks passed; no remediation required."
            outcome_mode = "healthy"
        elif health_bad or pm2_target:
            target = pm2_target or "signyn"
            if target not in allowlist:
                target = next(
                    (
                        n
                        for n in (
                            "signyn",
                            "signyardsnext",
                            "websites",
                            "node-server",
                        )
                        if n in allowlist
                    ),
                    next(iter(sorted(allowlist)), "signyn"),
                )
            target_proc = next(
                (p for p in pm2_procs if p.get("name") == target),
                None,
            )
            hypotheses = [
                {
                    "hypothesis": (
                        f"Application issue: health_check failed (HTTP {http_status}) "
                        f"and/or PM2 '{target}' unhealthy"
                    ),
                    "evidence_for": (
                        f"report={report[:180]!r}, http={http_status}, "
                        f"memory={memory}%, pm2_target={target}, status={target_proc}, "
                        f"top_process={top_proc.get('name')}"
                    ),
                    "evidence_against": (
                        "MySQL connections look healthy"
                        if mysql_healthy
                        else "MySQL also looks degraded"
                    ),
                    "score": 0.86,
                    "selected": True,
                },
                {
                    "hypothesis": "MySQL is the primary root cause",
                    "evidence_for": f"mysql={mysql.get('mysql')}",
                    "evidence_against": f"healthy={mysql_healthy}",
                    "score": 0.25,
                    "selected": False,
                },
                {
                    "hypothesis": "EC2 / nginx failure",
                    "evidence_for": f"http={http_status}",
                    "evidence_against": (
                        f"ec2={ec2['ec2'].get('state')}, nginx={nginx['nginx'].get('status')}"
                    ),
                    "score": 0.12,
                    "selected": False,
                },
            ]
            proposed_action = "restart_pm2_process"
            parameters = {"process_name": target}
            rationale = (
                f"Live checks indicate a problem (HTTP {http_status}, "
                f"PM2 target '{target}'). Low-risk restart is allowlisted."
            )
            outcome_mode = "remediate"
        else:
            hypotheses = [
                {
                    "hypothesis": "Unhealthy Node/PM2 process under memory pressure",
                    "evidence_for": (
                        f"memory={memory}%, "
                        f"swap={metrics['metrics'].get('swap_utilization')}, "
                        f"pm2={pm2_procs}"
                    ),
                    "evidence_against": "MySQL may be healthy",
                    "score": 0.8,
                    "selected": True,
                }
            ]
            proposed_action = "restart_pm2_process"
            parameters = {
                "process_name": (
                    "api" if "api" in allowlist else next(iter(sorted(allowlist)))
                )
            }
            rationale = "Mock/default path: restart allowlisted PM2 process."
            outcome_mode = "remediate"

        selected = next(h for h in hypotheses if h["selected"])
        for item in hypotheses:
            service.add_hypothesis(
                incident_id,
                hypothesis=item["hypothesis"],
                evidence_for=item["evidence_for"],
                evidence_against=item["evidence_against"],
                score=normalize_confidence(item["score"]),
                selected=item["selected"],
            )

        confidence = normalize_confidence(selected["score"])
        incident.root_cause = selected["hypothesis"]
        incident.confidence = confidence
        db.commit()

        if outcome_mode == "healthy":
            endpoint = (
                health.get("health", {}).get("endpoint")
                or settings.aegis_healthcheck_url
            )
            if mentions_db:
                summary = (
                    f"Checked live MySQL for: {report[:280]!r}. "
                    f"{mysql_summary['detail']}. No remediation was needed."
                )
                message = "MySQL looks healthy"
            else:
                summary = (
                    f"Checked live evidence for: {report[:280]!r}. "
                    f"HTTP {http_status} from {endpoint}; allowlisted PM2 apps are online; "
                    f"MySQL: {mysql_summary['detail']}. No remediation was needed."
                )
                message = "Site/service appears healthy"
            service.finalize(
                incident,
                status=IncidentStatus.RECOVERED,
                summary=summary,
                root_cause=selected["hypothesis"],
                confidence=confidence,
            )
            return {
                "status": IncidentStatus.RECOVERED.value,
                "message": message,
                "root_cause": selected["hypothesis"],
                "confidence": confidence,
            }

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
            approved_by=(
                "policy-auto"
                if decision.allowed and not decision.approval_required
                else None
            ),
        )

        # 5) Execute / await approval / escalate + verify
        return execute_approved_plan(
            db,
            incident_id,
            already_approved=False,
            summary=(
                "Deterministic agents investigated with live tool evidence "
                "(health, CloudWatch, PM2 websites/node-server), applied policy, "
                "executed remediation when justified, and verified recovery."
            ),
        )
    finally:
        current_incident_id.reset(token)


def resume_deterministic_incident(db: Session, incident_id: str) -> dict[str, Any]:
    """Continue after human approval."""
    return execute_approved_plan(db, incident_id, already_approved=True)
