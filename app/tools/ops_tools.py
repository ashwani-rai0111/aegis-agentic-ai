"""Typed operations tools. Backed by local mocks today; same names later map to AWS."""

from __future__ import annotations

import json
from typing import Any, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.tools.context import require_incident_id
from app.tools.mock_state import mock_infra


def _dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, default=str)


class AlarmInput(BaseModel):
    alarm_name: str = Field(..., description="CloudWatch alarm name")


class MetricInput(BaseModel):
    metric: str = Field(..., description="Metric name, e.g. memory_utilization")
    period: int = Field(default=300, description="Period in seconds")
    statistic: str = Field(default="Average", description="Statistic type")


class LogsInput(BaseModel):
    service: str = Field(..., description="Service name")
    time_range_minutes: int = Field(default=30, description="How far back to query")
    filter: str = Field(default="", description="Optional log filter")


class EmptyInput(BaseModel):
    note: str = Field(
        default="",
        description="Optional note; leave empty. Included so tool schemas are non-empty.",
    )


class ProcessInput(BaseModel):
    process_name: str = Field(..., description="PM2 process name")


class ReportInput(BaseModel):
    summary: str = Field(..., description="Final incident summary")
    root_cause: str = Field(..., description="Selected root cause")
    confidence: float = Field(..., description="Confidence 0-1")


class GetCloudWatchAlarmTool(BaseTool):
    name: str = "get_cloudwatch_alarm"
    description: str = "Read a CloudWatch alarm state and reason for the incident."
    args_schema: Type[BaseModel] = AlarmInput

    def _run(self, alarm_name: str) -> str:
        state = mock_infra.get(require_incident_id())
        alarm = state["alarm"]
        return _dumps(
            {
                "requested_alarm": alarm_name,
                "alarm_name": alarm["alarm_name"],
                "state": alarm["state"],
                "reason": alarm["reason"],
                "metric": alarm["metric"],
            }
        )


class GetCloudWatchMetricTool(BaseTool):
    name: str = "get_cloudwatch_metric"
    description: str = "Read a CloudWatch metric value for the monitored instance/service."
    args_schema: Type[BaseModel] = MetricInput

    def _run(self, metric: str, period: int = 300, statistic: str = "Average") -> str:
        state = mock_infra.get(require_incident_id())
        value = state["metrics"].get(metric)
        return _dumps(
            {
                "metric": metric,
                "period": period,
                "statistic": statistic,
                "value": value,
                "unit": "Percent" if "utilization" in metric else "Count",
                "available_metrics": list(state["metrics"].keys()),
            }
        )


class QueryLogsTool(BaseTool):
    name: str = "query_logs"
    description: str = "Query recent application/system logs for a service."
    args_schema: Type[BaseModel] = LogsInput

    def _run(self, service: str, time_range_minutes: int = 30, filter: str = "") -> str:
        state = mock_infra.get(require_incident_id())
        lines = state["logs"]
        if filter:
            lines = [line for line in lines if filter.lower() in line.lower()]
        return _dumps(
            {
                "service": service,
                "time_range_minutes": time_range_minutes,
                "filter": filter,
                "lines": lines,
            }
        )


class GetSystemMetricsTool(BaseTool):
    name: str = "get_system_metrics"
    description: str = "Get host CPU/memory/swap/disk and key app metrics via mock SSM."
    args_schema: Type[BaseModel] = EmptyInput

    def _run(self, note: str = "") -> str:
        state = mock_infra.get(require_incident_id())
        return _dumps(
            {
                "instance_id": state["instance_id"],
                "metrics": state["metrics"],
                "remediated": state["remediated"],
                "note": note,
            }
        )


class GetPm2StatusTool(BaseTool):
    name: str = "get_pm2_status"
    description: str = "Get PM2 process status on the target instance."
    args_schema: Type[BaseModel] = EmptyInput

    def _run(self, note: str = "") -> str:
        state = mock_infra.get(require_incident_id())
        return _dumps(
            {
                "instance_id": state["instance_id"],
                "processes": state["pm2"]["processes"],
                "note": note,
            }
        )


class RestartPm2ProcessTool(BaseTool):
    name: str = "restart_pm2_process"
    description: str = (
        "Restart a specific PM2 process through a controlled command template. "
        "Only use after safety approval for an allowlisted remediation."
    )
    args_schema: Type[BaseModel] = ProcessInput

    def _run(self, process_name: str) -> str:
        result = mock_infra.restart_pm2_process(require_incident_id(), process_name)
        return _dumps(result)


class CreateIncidentReportTool(BaseTool):
    name: str = "create_incident_report"
    description: str = "Create the final structured incident report summary."
    args_schema: Type[BaseModel] = ReportInput

    def _run(self, summary: str, root_cause: str, confidence: float) -> str:
        return _dumps(
            {
                "incident_id": require_incident_id(),
                "summary": summary,
                "root_cause": root_cause,
                "confidence": confidence,
                "status": "report_ready",
            }
        )


def build_read_tools() -> list[BaseTool]:
    return [
        GetCloudWatchAlarmTool(),
        GetCloudWatchMetricTool(),
        QueryLogsTool(),
        GetSystemMetricsTool(),
        GetPm2StatusTool(),
    ]


def build_action_tools() -> list[BaseTool]:
    return [RestartPm2ProcessTool()]


def build_report_tools() -> list[BaseTool]:
    return [CreateIncidentReportTool()]