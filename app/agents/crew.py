"""CrewAI multi-agent incident response crew (full specialized roster)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from crewai import Agent, Crew, Process, Task
from sqlalchemy.orm import Session

from app.agents.confidence import normalize_confidence
from app.agents.issue_focus import build_focused_live_answer, summarize_mysql_for_question
from app.config import get_settings
from app.models.enums import IncidentStatus
from app.policies.safety import evaluate_action
from app.services.incident_service import IncidentService
from app.services.remediation import execute_approved_plan
from app.tools.backend import get_tool_backend
from app.tools.context import current_incident_id
from app.tools.mock_state import mock_infra
from app.tools.ops_tools import (
    build_database_tools,
    build_infra_tools,
    build_log_tools,
    build_monitoring_tools,
    build_read_tools,
)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def run_crewai_incident(
    db: Session,
    incident_id: str,
    *,
    user_message: str | None = None,
) -> dict[str, Any]:
    """Run CrewAI for reasoning; Python enforces safety + recovery + verification."""
    settings = get_settings()
    if settings.openai_api_key:
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    os.environ.setdefault("OPENAI_MODEL_NAME", settings.openai_model_name)

    service = IncidentService(db)
    incident = service.get(incident_id)
    if not incident:
        raise ValueError(f"Incident not found: {incident_id}")

    report = (user_message or incident.summary or "").strip()
    token = current_incident_id.set(incident_id)
    try:
        service.transition(incident, IncidentStatus.TRIAGING)
        service.transition(incident, IncidentStatus.INVESTIGATING)

        allowlist = ",".join(sorted(settings.pm2_allowlist()))
        crew = _build_full_crew(settings.aegis_verbose)
        if mock_infra.has(incident_id):
            alarm_name = mock_infra.get(incident_id)["alarm"]["alarm_name"]
        else:
            alarm_name = settings.aegis_cw_alarm_name or "unknown"
        result = crew.kickoff(
            inputs={
                "incident_id": incident_id,
                "service": incident.service,
                "scenario": incident.scenario,
                "alarm_name": alarm_name,
                "user_message": report or "(none — alarm-driven)",
                "pm2_allowlist": allowlist,
            }
        )

        plan_output = _task_raw(result, -1)
        rca_output = _task_raw(result, -2)

        try:
            rca_data = _extract_json(rca_output)
        except Exception:
            rca_data = {
                "hypotheses": [
                    {
                        "hypothesis": "Unhealthy Node API process memory pressure",
                        "evidence_for": rca_output[:500],
                        "evidence_against": "n/a",
                        "score": 0.7,
                        "selected": True,
                    }
                ],
                "root_cause": "Unhealthy Node API process memory pressure",
                "confidence": 0.7,
            }

        service.transition(incident, IncidentStatus.HYPOTHESIS_READY)
        for item in rca_data.get("hypotheses", []):
            service.add_hypothesis(
                incident_id,
                hypothesis=str(item.get("hypothesis", "unknown")),
                evidence_for=str(item.get("evidence_for", "")),
                evidence_against=str(item.get("evidence_against", "")),
                score=normalize_confidence(item.get("score", 0.0)),
                selected=bool(item.get("selected", False)),
            )
        root_cause = str(rca_data.get("root_cause", "Unknown"))
        confidence = normalize_confidence(rca_data.get("confidence", 0.5))
        incident.root_cause = root_cause
        incident.confidence = confidence
        db.commit()

        try:
            plan_data = _extract_json(plan_output)
        except Exception:
            plan_data = {
                "proposed_action": "restart_pm2_process",
                "parameters": {"process_name": "api"},
                "risk": "LOW",
                "rationale": plan_output[:500],
                "approval_required": False,
            }

        # Live evidence gate: answer the user's actual question (website vs
        # node-server vs MySQL), instead of always returning the same stack blurb.
        if not mock_infra.has(incident_id):
            backend = get_tool_backend(incident_id)
            live_health = backend.health_check()
            live_pm2 = backend.get_pm2_status()
            live_mysql = backend.get_mysql_status()
            allowlist = settings.pm2_allowlist()
            mysql_block = live_mysql.get("mysql") or {}
            mysql_summary = summarize_mysql_for_question(mysql_block, report)
            answer = build_focused_live_answer(
                report=report,
                health_block=live_health,
                processes=live_pm2.get("processes") or [],
                mysql_summary=mysql_summary,
                allowlist=allowlist,
                fallback_endpoint=settings.aegis_healthcheck_url,
            )

            for source, name, value, evidence in answer.get("observations") or []:
                service.add_observation(
                    incident_id,
                    source=source,
                    name=name,
                    value=str(value),
                    evidence=evidence if isinstance(evidence, dict) else {"value": evidence},
                )

            if answer["healthy"]:
                healthy_cause = str(answer["root_cause"])
                incident.root_cause = healthy_cause
                incident.confidence = max(confidence, 0.9)
                db.commit()
                service.add_hypothesis(
                    incident_id,
                    hypothesis=healthy_cause,
                    evidence_for=str(answer.get("detail") or ""),
                    evidence_against="n/a",
                    score=0.9,
                    selected=True,
                )
                service.finalize(
                    incident,
                    status=IncidentStatus.RECOVERED,
                    summary=str(answer["summary"]),
                    root_cause=healthy_cause,
                    confidence=0.9,
                )
                return {
                    "status": IncidentStatus.RECOVERED.value,
                    "message": healthy_cause,
                    "root_cause": healthy_cause,
                    "confidence": 0.9,
                    "crew_raw": str(result),
                    "focus": answer.get("focus"),
                }

            # Focused unhealthy path — force a plan matching the question.
            if answer.get("proposed_action") == "restart_mysql":
                plan_data = {
                    "proposed_action": "restart_mysql",
                    "parameters": {},
                    "risk": "MEDIUM",
                    "rationale": answer["root_cause"],
                    "approval_required": True,
                }
            elif answer.get("proposed_action") == "restart_pm2_process":
                plan_data = {
                    "proposed_action": "restart_pm2_process",
                    "parameters": {
                        "process_name": answer.get("restart_target") or "node-server"
                    },
                    "risk": "LOW",
                    "rationale": answer["root_cause"],
                    "approval_required": False,
                }
            root_cause = str(answer["root_cause"])
            confidence = 0.9
            incident.root_cause = root_cause
            incident.confidence = confidence
            db.commit()
            service.add_hypothesis(
                incident_id,
                hypothesis=root_cause,
                evidence_for=str(answer.get("detail") or ""),
                evidence_against="Other stack components may still look fine",
                score=0.9,
                selected=True,
            )

        service.transition(incident, IncidentStatus.PLAN_READY)
        proposed_action = str(plan_data.get("proposed_action", "restart_pm2_process"))
        parameters = plan_data.get("parameters") or {}
        if proposed_action == "restart_pm2_process" and "process_name" not in parameters:
            parameters = {"process_name": "api"}

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
            rationale=str(plan_data.get("rationale", "")),
            approval_required=decision.approval_required,
            approved=decision.allowed and not decision.approval_required,
            approved_by="policy-auto" if decision.allowed and not decision.approval_required else None,
        )

        # Persist a compact observation set for the timeline
        before = get_tool_backend(incident_id).snapshot()
        for key, value in (before.get("metrics") or {}).items():
            service.add_observation(
                incident_id,
                source="system",
                name=key,
                value=str(value),
                evidence={"value": value},
            )
        service.add_observation(
            incident_id,
            source="cloudwatch",
            name="alarm",
            value=str(before.get("alarm", {}).get("state")),
            evidence=before.get("alarm"),
        )
        service.add_observation(
            incident_id,
            source="crew",
            name="investigation_summary",
            value=str(result)[:2000],
            evidence={"crew_raw": str(result)[:4000]},
        )

        outcome = execute_approved_plan(
            db,
            incident_id,
            already_approved=False,
            summary=(
                "CrewAI specialized agents (monitoring, logs, infra, database, diagnosis, "
                "planner) investigated with tools; recovery/verification ran under safety policy."
            ),
        )
        outcome["crew_raw"] = str(result)
        return outcome
    finally:
        current_incident_id.reset(token)


def resume_crewai_incident(db: Session, incident_id: str) -> dict[str, Any]:
    return execute_approved_plan(db, incident_id, already_approved=True)


def _build_full_crew(verbose: bool) -> Crew:
    monitoring_tools = build_monitoring_tools()
    log_tools = build_log_tools()
    infra_tools = build_infra_tools()
    db_tools = build_database_tools()
    # Diagnosis/planner can review any read tool output via context; give diagnosis broad reads.
    diagnosis_tools = build_read_tools()

    incident_manager = Agent(
        role="Incident Manager Agent",
        goal="Understand what is happening and coordinate a focused investigation.",
        backstory=(
            "Senior incident commander. Summarizes the alarm, sets investigation priorities, "
            "and never jumps to remediation before evidence is collected."
        ),
        allow_delegation=False,
        verbose=verbose,
    )
    monitoring = Agent(
        role="Monitoring Agent",
        goal="Gather CloudWatch/host metrics and HTTP health signals.",
        backstory="SRE monitoring specialist who always uses tools before concluding.",
        tools=monitoring_tools,
        allow_delegation=False,
        verbose=verbose,
    )
    log_analyst = Agent(
        role="Log Analyst Agent",
        goal="Analyze application and PM2 logs to identify error patterns.",
        backstory="Log forensics specialist who correlates timestamps with symptoms.",
        tools=log_tools,
        allow_delegation=False,
        verbose=verbose,
    )
    infra = Agent(
        role="Infrastructure Agent",
        goal="Investigate EC2, nginx, PM2, and top host processes.",
        backstory=(
            "Infrastructure engineer. Uses tools based on current state — if memory is high, "
            "inspect processes; if HTTP is bad, check nginx and EC2."
        ),
        tools=infra_tools,
        allow_delegation=False,
        verbose=verbose,
    )
    database = Agent(
        role="Database Agent",
        goal="Investigate MySQL before anyone restarts application processes.",
        backstory=(
            "DBA on-call. Checks connections, buffer pool, and threads. Can clear MySQL as "
            "a culprit when it looks healthy."
        ),
        tools=db_tools,
        allow_delegation=False,
        verbose=verbose,
    )
    diagnosis = Agent(
        role="Diagnosis Agent",
        goal="Select the most probable root cause with scored hypotheses.",
        backstory=(
            "Evidence-driven RCA specialist. Performs differential diagnosis: do not blame "
            "MySQL if connections are healthy; prefer Node/PM2 when the api process is unhealthy."
        ),
        tools=diagnosis_tools,
        allow_delegation=False,
        verbose=verbose,
    )
    planner = Agent(
        role="Decision / Planner Agent",
        goal="Propose the lowest-risk allowlisted remediation with clear risk tier.",
        backstory=(
            "Prefers LOW risk actions (restart_pm2_process, clear_temp_files, rotate_logs). "
            "Uses MEDIUM actions (restart_mysql, scale_ec2, change_configuration) only when "
            "evidence requires them and notes approval_required=true. Never proposes "
            "DROP DATABASE, terminate EC2, delete data, or modify IAM."
        ),
        allow_delegation=False,
        verbose=verbose,
    )

    manage_task = Task(
        description=(
            "Incident {incident_id} for service {service} (scenario={scenario}). "
            "Operator/user report: '{user_message}'. "
            "Also consider CloudWatch alarm '{alarm_name}'. "
            "As Incident Manager, interpret the report (e.g. website down → check "
            "health_check + PM2 websites/node-server). Return JSON with keys: "
            "situation, priorities, suspected_pm2_processes."
        ),
        expected_output="JSON investigation brief",
        agent=incident_manager,
    )
    monitor_task = Task(
        description=(
            "For incident {incident_id}, confirm alarm '{alarm_name}', "
            "collect cpu/memory/swap/disk metrics, and run health_check "
            "(critical for website-down reports). Return JSON."
        ),
        expected_output="JSON with alarm, metrics, health",
        agent=monitoring,
        context=[manage_task],
    )
    logs_task = Task(
        description=(
            "Analyze logs for service {service}. Call query_logs and get_pm2_logs for "
            "process_name=websites and process_name=node-server (and api if present). "
            "Highlight patterns for site outages vs memory pressure. Return JSON."
        ),
        expected_output="JSON log analysis",
        agent=log_analyst,
        context=[manage_task, monitor_task],
    )
    infra_task = Task(
        description=(
            "Investigate infrastructure for incident {incident_id}. Call get_ec2_status, "
            "get_nginx_status, get_process_memory / get_processes, and get_pm2_status. "
            "Focus on PM2 apps in allowlist: {pm2_allowlist}. Return JSON."
        ),
        expected_output="JSON infra evidence",
        agent=infra,
        context=[manage_task, monitor_task],
    )
    db_task = Task(
        description=(
            "Investigate MySQL for incident {incident_id}. Call get_mysql_status (and "
            "query_logs if needed). Inspect production and staging database probes, "
            "service status, connections, and threads_running. Explicitly conclude "
            "whether MySQL is healthy or the likely root cause. Return JSON."
        ),
        expected_output="JSON MySQL assessment",
        agent=database,
        context=[manage_task, monitor_task, logs_task],
    )
    rca_task = Task(
        description=(
            "Using all prior evidence and the user report '{user_message}', produce scored "
            "hypotheses and select root cause. Return JSON with hypotheses[], root_cause, "
            "confidence. For website/signyn reports prefer PM2 websites or node-server "
            "when unhealthy or health_check failed; prefer MySQL only when DB is degraded."
        ),
        expected_output="JSON RCA result",
        agent=diagnosis,
        context=[monitor_task, logs_task, infra_task, db_task],
    )
    plan_task = Task(
        description=(
            "Propose remediation JSON with proposed_action, parameters, risk "
            "(LOW|MEDIUM|HIGH|CRITICAL), rationale, approval_required. "
            "Allowlisted actions: restart_pm2_process with process_name in "
            "[{pm2_allowlist}], clear_temp_files, rotate_logs, restart_mysql, "
            "scale_ec2, change_configuration. Prefer restart_pm2_process on "
            "Never propose destructive actions. If health_check is 2xx and PM2 apps are "
            "online, do NOT invent an outage — propose no remediation / note site is healthy."
        ),
        expected_output="JSON plan",
        agent=planner,
        context=[rca_task],
    )

    return Crew(
        agents=[
            incident_manager,
            monitoring,
            log_analyst,
            infra,
            database,
            diagnosis,
            planner,
        ],
        tasks=[
            manage_task,
            monitor_task,
            logs_task,
            infra_task,
            db_task,
            rca_task,
            plan_task,
        ],
        process=Process.sequential,
        verbose=verbose,
    )


def _task_raw(crew_result: Any, index: int) -> str:
    tasks_output = getattr(crew_result, "tasks_output", None) or []
    if tasks_output:
        try:
            return str(tasks_output[index])
        except Exception:
            pass
    return str(crew_result)
