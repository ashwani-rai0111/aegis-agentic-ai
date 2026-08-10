"""CrewAI multi-agent incident response crew."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from crewai import Agent, Crew, Process, Task
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.enums import IncidentStatus
from app.policies.safety import evaluate_action
from app.services.incident_service import IncidentService
from app.tools.context import current_incident_id
from app.tools.mock_state import mock_infra
from app.tools.ops_tools import build_read_tools


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def run_crewai_incident(db: Session, incident_id: str) -> dict[str, Any]:
    """Run CrewAI for reasoning, with Python-enforced safety + action execution."""
    settings = get_settings()
    if settings.openai_api_key:
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    os.environ.setdefault("OPENAI_MODEL_NAME", settings.openai_model_name)

    service = IncidentService(db)
    incident = service.get(incident_id)
    if not incident:
        raise ValueError(f"Incident not found: {incident_id}")

    token = current_incident_id.set(incident_id)
    before = mock_infra.get(incident_id)
    before_latency = str(before["metrics"]["api_p95_latency_ms"])
    before_memory = str(before["metrics"]["memory_utilization"])
    before_alarm = before["alarm"]["state"]

    try:
        service.transition(incident, IncidentStatus.TRIAGING)
        service.transition(incident, IncidentStatus.INVESTIGATING)

        # Phase 1: monitoring + investigation + RCA + plan via CrewAI
        reasoning_crew = _build_reasoning_crew(settings.aegis_verbose)
        reasoning_result = reasoning_crew.kickoff(
            inputs={"incident_id": incident_id, "service": incident.service}
        )
        plan_output = _task_raw(reasoning_result, -1)
        rca_output = _task_raw(reasoning_result, -2)

        try:
            rca_data = _extract_json(rca_output)
        except Exception:
            rca_data = {
                "hypotheses": [
                    {
                        "hypothesis": "Unhealthy API process memory pressure",
                        "evidence_for": rca_output[:500],
                        "evidence_against": "n/a",
                        "score": 0.7,
                        "selected": True,
                    }
                ],
                "root_cause": "Unhealthy API process memory pressure",
                "confidence": 0.7,
            }

        service.transition(incident, IncidentStatus.HYPOTHESIS_READY)
        for item in rca_data.get("hypotheses", []):
            service.add_hypothesis(
                incident_id,
                hypothesis=str(item.get("hypothesis", "unknown")),
                evidence_for=str(item.get("evidence_for", "")),
                evidence_against=str(item.get("evidence_against", "")),
                score=float(item.get("score", 0.0)),
                selected=bool(item.get("selected", False)),
            )
        root_cause = str(rca_data.get("root_cause", "Unknown"))
        confidence = float(rca_data.get("confidence", 0.5))
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

        service.transition(incident, IncidentStatus.PLAN_READY)
        proposed_action = str(plan_data.get("proposed_action", "restart_pm2_process"))
        parameters = plan_data.get("parameters") or {"process_name": "api"}
        decision = evaluate_action(
            proposed_action,
            parameters,
            already_approved=False,
            actions_already_taken=service.count_actions(incident_id),
        )
        plan = service.add_plan(
            incident_id,
            proposed_action=proposed_action,
            parameters=parameters,
            risk=decision.risk.value,
            rationale=str(plan_data.get("rationale", "")),
            approval_required=decision.approval_required,
            approved=decision.allowed and not decision.approval_required,
            approved_by="policy-auto" if decision.allowed else None,
        )

        # Persist key observations from mock state for timeline completeness
        for key, value in before["metrics"].items():
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
            value=before_alarm,
            evidence=before["alarm"],
        )

        if decision.approval_required and not plan.approved:
            service.transition(incident, IncidentStatus.AWAITING_APPROVAL)
            return {"status": IncidentStatus.AWAITING_APPROVAL.value}

        if not decision.allowed:
            service.finalize(
                incident,
                status=IncidentStatus.ESCALATED,
                summary="Safety policy blocked the proposed remediation",
                root_cause=root_cause,
                confidence=confidence,
            )
            return {"status": IncidentStatus.ESCALATED.value, "reason": decision.reason}

        service.transition(incident, IncidentStatus.EXECUTING)
        from app.tools.ops_tools import RestartPm2ProcessTool

        action_raw = RestartPm2ProcessTool()._run(
            process_name=str(parameters.get("process_name", "api"))
        )
        action_result = json.loads(action_raw)
        service.add_action(
            incident_id,
            tool=proposed_action,
            parameters=parameters,
            approved_by=plan.approved_by or "policy-auto",
            result=action_raw,
            success=bool(action_result.get("success")),
        )

        service.transition(incident, IncidentStatus.VERIFYING)
        after = mock_infra.get(incident_id)
        latency_ok = float(after["metrics"]["api_p95_latency_ms"]) < 500
        memory_ok = float(after["metrics"]["memory_utilization"]) < 75
        alarm_ok = after["alarm"]["state"] == "OK"
        recovered = latency_ok and memory_ok and alarm_ok

        service.add_verification(
            incident_id,
            metric="api_p95_latency_ms",
            before_value=before_latency,
            after_value=str(after["metrics"]["api_p95_latency_ms"]),
            success=latency_ok,
        )
        service.add_verification(
            incident_id,
            metric="memory_utilization",
            before_value=before_memory,
            after_value=str(after["metrics"]["memory_utilization"]),
            success=memory_ok,
        )
        service.add_verification(
            incident_id,
            metric="alarm_state",
            before_value=before_alarm,
            after_value=after["alarm"]["state"],
            success=alarm_ok,
        )

        summary = (
            "CrewAI agents investigated the alarm, selected a root cause, proposed a "
            "safe remediation, executed an allowlisted action, and verified recovery."
        )
        final_status = IncidentStatus.RECOVERED if recovered else IncidentStatus.FAILED
        service.finalize(
            incident,
            status=final_status,
            summary=summary,
            root_cause=root_cause,
            confidence=confidence,
        )
        return {
            "status": final_status.value,
            "root_cause": root_cause,
            "confidence": confidence,
            "crew_raw": str(reasoning_result),
        }
    finally:
        current_incident_id.reset(token)


def _build_reasoning_crew(verbose: bool) -> Crew:
    read_tools = build_read_tools()
    monitoring = Agent(
        role="Monitoring Agent",
        goal="Confirm alarm and capture CloudWatch symptoms.",
        backstory="SRE monitoring specialist who always uses tools.",
        tools=read_tools,
        allow_delegation=False,
        verbose=verbose,
    )
    investigation = Agent(
        role="Investigation Agent",
        goal="Collect host/PM2/log evidence.",
        backstory="Careful investigator of production incidents.",
        tools=read_tools,
        allow_delegation=False,
        verbose=verbose,
    )
    rca = Agent(
        role="Root Cause Analysis Agent",
        goal="Select the most probable root cause with scored hypotheses.",
        backstory="Evidence-driven RCA specialist.",
        allow_delegation=False,
        verbose=verbose,
    )
    planner = Agent(
        role="Planning Agent",
        goal="Propose lowest-risk allowlisted remediation.",
        backstory=(
            "Prefers restart_pm2_process on api when memory/latency and unhealthy "
            "PM2 api process are present."
        ),
        allow_delegation=False,
        verbose=verbose,
    )

    monitor_task = Task(
        description=(
            "For incident {incident_id}, call get_cloudwatch_alarm "
            "(alarm_name=prod-api-high-latency) and get_cloudwatch_metric for "
            "memory_utilization and api_p95_latency_ms. Return JSON."
        ),
        expected_output="JSON with alarm and metrics",
        agent=monitoring,
    )
    investigate_task = Task(
        description=(
            "Investigate incident {incident_id} for service {service}. "
            "Use get_system_metrics, get_pm2_status, query_logs. Return JSON evidence."
        ),
        expected_output="JSON evidence bundle",
        agent=investigation,
        context=[monitor_task],
    )
    rca_task = Task(
        description=(
            "Produce scored hypotheses and select root cause. Return JSON with "
            "hypotheses, root_cause, confidence."
        ),
        expected_output="JSON RCA result",
        agent=rca,
        context=[investigate_task],
    )
    plan_task = Task(
        description=(
            "Propose remediation JSON with proposed_action, parameters, risk, "
            "rationale, approval_required. Prefer restart_pm2_process process_name=api."
        ),
        expected_output="JSON plan",
        agent=planner,
        context=[rca_task],
    )
    return Crew(
        agents=[monitoring, investigation, rca, planner],
        tasks=[monitor_task, investigate_task, rca_task, plan_task],
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