from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import get_settings
from app.models.enums import RiskLevel

READ_ONLY_TOOLS = {
    "get_cloudwatch_alarm",
    "get_cloudwatch_metric",
    "get_cpu_usage",
    "get_memory_usage",
    "get_disk_usage",
    "get_swap_usage",
    "get_system_metrics",
    "get_processes",
    "get_process_memory",
    "query_logs",
    "get_pm2_status",
    "get_pm2_logs",
    "get_mysql_status",
    "get_nginx_status",
    "get_ec2_status",
    "health_check",
    "create_incident_report",
}

# Green / yellow / red style controls for production-grade autonomy.
ALLOWLISTED_ACTIONS: dict[str, dict[str, Any]] = {
    # LOW — agent may auto-execute
    "restart_pm2_process": {
        "risk": RiskLevel.LOW,
        "approval_required": False,
        "allowed_params": {"process_name": {"api", "worker"}},
    },
    "clear_temp_files": {
        "risk": RiskLevel.LOW,
        "approval_required": False,
        "allowed_params": {},
    },
    "rotate_logs": {
        "risk": RiskLevel.LOW,
        "approval_required": False,
        "allowed_params": {},
    },
    # MEDIUM — require human approval
    "restart_mysql": {
        "risk": RiskLevel.MEDIUM,
        "approval_required": True,
        "allowed_params": {},
    },
    "change_configuration": {
        "risk": RiskLevel.MEDIUM,
        "approval_required": True,
        "allowed_params": {},
    },
    "scale_ec2": {
        "risk": RiskLevel.MEDIUM,
        "approval_required": True,
        "allowed_params": {},
    },
    # HIGH / CRITICAL — never auto-execute (blocked even if somehow proposed)
    "terminate_instance": {
        "risk": RiskLevel.CRITICAL,
        "approval_required": True,
        "allowed_params": {},
        "never_auto": True,
    },
    "drop_database": {
        "risk": RiskLevel.CRITICAL,
        "approval_required": True,
        "allowed_params": {},
        "never_auto": True,
    },
    "delete_production_data": {
        "risk": RiskLevel.CRITICAL,
        "approval_required": True,
        "allowed_params": {},
        "never_auto": True,
    },
    "modify_iam": {
        "risk": RiskLevel.CRITICAL,
        "approval_required": True,
        "allowed_params": {},
        "never_auto": True,
    },
}


@dataclass
class SafetyDecision:
    allowed: bool
    approval_required: bool
    risk: RiskLevel
    reason: str


def evaluate_action(
    tool: str,
    parameters: dict[str, Any] | None,
    *,
    already_approved: bool = False,
    actions_already_taken: int = 0,
) -> SafetyDecision:
    settings = get_settings()
    parameters = parameters or {}

    if tool in READ_ONLY_TOOLS:
        return SafetyDecision(
            allowed=True,
            approval_required=False,
            risk=RiskLevel.LOW,
            reason="Read-only tool is always permitted",
        )

    if tool not in ALLOWLISTED_ACTIONS:
        return SafetyDecision(
            allowed=False,
            approval_required=False,
            risk=RiskLevel.CRITICAL,
            reason=f"Tool '{tool}' is not in the action allowlist",
        )

    if actions_already_taken >= settings.max_actions_per_incident:
        return SafetyDecision(
            allowed=False,
            approval_required=False,
            risk=RiskLevel.HIGH,
            reason=(
                f"Action limit reached "
                f"({settings.max_actions_per_incident} per incident)"
            ),
        )

    policy = ALLOWLISTED_ACTIONS[tool]
    risk = policy["risk"]
    approval_required = bool(policy["approval_required"])
    never_auto = bool(policy.get("never_auto", False))

    for key, allowed_values in policy.get("allowed_params", {}).items():
        if key not in parameters:
            return SafetyDecision(
                allowed=False,
                approval_required=approval_required,
                risk=risk,
                reason=f"Missing required parameter '{key}'",
            )
        if allowed_values and parameters[key] not in allowed_values:
            return SafetyDecision(
                allowed=False,
                approval_required=approval_required,
                risk=risk,
                reason=f"Parameter '{key}={parameters[key]}' is not allowlisted",
            )

    # Critical destructive actions are never executed by the agent control plane.
    if never_auto:
        return SafetyDecision(
            allowed=False,
            approval_required=True,
            risk=risk,
            reason=(
                f"Action '{tool}' is permanently blocked from autonomous execution "
                "(critical / destructive)"
            ),
        )

    if approval_required and not already_approved:
        return SafetyDecision(
            allowed=False,
            approval_required=True,
            risk=risk,
            reason="Human approval required before execution",
        )

    return SafetyDecision(
        allowed=True,
        approval_required=approval_required,
        risk=risk,
        reason="Action permitted by safety policy",
    )
