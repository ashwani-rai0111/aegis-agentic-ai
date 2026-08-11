"""Typed operations tools. Backed by mock or AWS via get_tool_backend()."""

from __future__ import annotations

import json
from typing import Any, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.tools.backend import get_tool_backend
from app.tools.context import require_incident_id


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


class ScaleInput(BaseModel):
    desired_capacity: int = Field(..., description="Desired ASG/EC2 capacity")


class ConfigInput(BaseModel):
    key: str = Field(..., description="Configuration key")
    value: str = Field(..., description="Configuration value")


class ReportInput(BaseModel):
    summary: str = Field(..., description="Final incident summary")
    root_cause: str = Field(..., description="Selected root cause")
    confidence: float = Field(..., description="Confidence 0-1")


class GetCloudWatchAlarmTool(BaseTool):
    name: str = "get_cloudwatch_alarm"
    description: str = "Read a CloudWatch alarm state and reason for the incident."
    args_schema: Type[BaseModel] = AlarmInput

    def _run(self, alarm_name: str) -> str:
        return _dumps(get_tool_backend().get_cloudwatch_alarm(alarm_name))


class GetCloudWatchMetricTool(BaseTool):
    name: str = "get_cloudwatch_metric"
    description: str = "Read a CloudWatch metric value for the monitored instance/service."
    args_schema: Type[BaseModel] = MetricInput

    def _run(self, metric: str, period: int = 300, statistic: str = "Average") -> str:
        return _dumps(
            get_tool_backend().get_cloudwatch_metric(
                metric, period=period, statistic=statistic
            )
        )


class GetCpuUsageTool(BaseTool):
    name: str = "get_cpu_usage"
    description: str = "Get host CPU utilization."
    args_schema: Type[BaseModel] = EmptyInput

    def _run(self, note: str = "") -> str:
        return _dumps(get_tool_backend().get_cpu_usage(note=note))


class GetMemoryUsageTool(BaseTool):
    name: str = "get_memory_usage"
    description: str = "Get host memory utilization."
    args_schema: Type[BaseModel] = EmptyInput

    def _run(self, note: str = "") -> str:
        return _dumps(get_tool_backend().get_memory_usage(note=note))


class GetDiskUsageTool(BaseTool):
    name: str = "get_disk_usage"
    description: str = "Get host disk utilization."
    args_schema: Type[BaseModel] = EmptyInput

    def _run(self, note: str = "") -> str:
        return _dumps(get_tool_backend().get_disk_usage(note=note))


class GetSwapUsageTool(BaseTool):
    name: str = "get_swap_usage"
    description: str = "Get host swap utilization."
    args_schema: Type[BaseModel] = EmptyInput

    def _run(self, note: str = "") -> str:
        return _dumps(get_tool_backend().get_swap_usage(note=note))


class GetProcessesTool(BaseTool):
    name: str = "get_processes"
    description: str = "List top processes with memory/CPU (alias: get_process_memory)."
    args_schema: Type[BaseModel] = EmptyInput

    def _run(self, note: str = "") -> str:
        return _dumps(get_tool_backend().get_processes(note=note))


class GetProcessMemoryTool(BaseTool):
    name: str = "get_process_memory"
    description: str = "Identify which processes are consuming the most memory."
    args_schema: Type[BaseModel] = EmptyInput

    def _run(self, note: str = "") -> str:
        return GetProcessesTool()._run(note=note)


class QueryLogsTool(BaseTool):
    name: str = "query_logs"
    description: str = "Query recent application/system logs for a service."
    args_schema: Type[BaseModel] = LogsInput

    def _run(self, service: str, time_range_minutes: int = 30, filter: str = "") -> str:
        return _dumps(
            get_tool_backend().query_logs(
                service, time_range_minutes=time_range_minutes, filter=filter
            )
        )


class GetSystemMetricsTool(BaseTool):
    name: str = "get_system_metrics"
    description: str = "Get host CPU/memory/swap/disk and key app metrics (mock or SSM)."
    args_schema: Type[BaseModel] = EmptyInput

    def _run(self, note: str = "") -> str:
        return _dumps(get_tool_backend().get_system_metrics(note=note))


class GetPm2StatusTool(BaseTool):
    name: str = "get_pm2_status"
    description: str = "Get PM2 process status on the target instance."
    args_schema: Type[BaseModel] = EmptyInput

    def _run(self, note: str = "") -> str:
        return _dumps(get_tool_backend().get_pm2_status(note=note))


class GetPm2LogsTool(BaseTool):
    name: str = "get_pm2_logs"
    description: str = "Get recent PM2 logs for a process."
    args_schema: Type[BaseModel] = ProcessInput

    def _run(self, process_name: str) -> str:
        return _dumps(get_tool_backend().get_pm2_logs(process_name))


class GetMysqlStatusTool(BaseTool):
    name: str = "get_mysql_status"
    description: str = "Inspect MySQL health: connections, buffer pool, threads."
    args_schema: Type[BaseModel] = EmptyInput

    def _run(self, note: str = "") -> str:
        return _dumps(get_tool_backend().get_mysql_status(note=note))


class GetNginxStatusTool(BaseTool):
    name: str = "get_nginx_status"
    description: str = "Inspect nginx status and upstream health."
    args_schema: Type[BaseModel] = EmptyInput

    def _run(self, note: str = "") -> str:
        return _dumps(get_tool_backend().get_nginx_status(note=note))


class GetEc2StatusTool(BaseTool):
    name: str = "get_ec2_status"
    description: str = "Inspect EC2 instance state and status checks."
    args_schema: Type[BaseModel] = EmptyInput

    def _run(self, note: str = "") -> str:
        return _dumps(get_tool_backend().get_ec2_status(note=note))


class HealthCheckTool(BaseTool):
    name: str = "health_check"
    description: str = "HTTP health check against the application endpoint."
    args_schema: Type[BaseModel] = EmptyInput

    def _run(self, note: str = "") -> str:
        return _dumps(get_tool_backend().health_check(note=note))


class RestartPm2ProcessTool(BaseTool):
    name: str = "restart_pm2_process"
    description: str = (
        "Restart a specific PM2 process through a controlled command template. "
        "Only use after safety approval for an allowlisted remediation."
    )
    args_schema: Type[BaseModel] = ProcessInput

    def _run(self, process_name: str) -> str:
        return _dumps(get_tool_backend().restart_pm2_process(process_name))


class ClearTempFilesTool(BaseTool):
    name: str = "clear_temp_files"
    description: str = "Clear temporary files on the host (low risk)."
    args_schema: Type[BaseModel] = EmptyInput

    def _run(self, note: str = "") -> str:
        result = get_tool_backend().clear_temp_files()
        result["note"] = note
        return _dumps(result)


class RotateLogsTool(BaseTool):
    name: str = "rotate_logs"
    description: str = "Rotate application/system logs (low risk)."
    args_schema: Type[BaseModel] = EmptyInput

    def _run(self, note: str = "") -> str:
        result = get_tool_backend().rotate_logs()
        result["note"] = note
        return _dumps(result)


class RestartMysqlTool(BaseTool):
    name: str = "restart_mysql"
    description: str = "Restart MySQL service (medium risk; requires human approval)."
    args_schema: Type[BaseModel] = EmptyInput

    def _run(self, note: str = "") -> str:
        result = get_tool_backend().restart_mysql()
        result["note"] = note
        return _dumps(result)


class ScaleEc2Tool(BaseTool):
    name: str = "scale_ec2"
    description: str = "Scale EC2/ASG capacity (medium risk; requires human approval)."
    args_schema: Type[BaseModel] = ScaleInput

    def _run(self, desired_capacity: int) -> str:
        return _dumps(get_tool_backend().scale_ec2(desired_capacity))


class ChangeConfigurationTool(BaseTool):
    name: str = "change_configuration"
    description: str = "Change a runtime configuration value (medium risk; requires approval)."
    args_schema: Type[BaseModel] = ConfigInput

    def _run(self, key: str, value: str) -> str:
        return _dumps(get_tool_backend().change_configuration(key, value))


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
        GetCpuUsageTool(),
        GetMemoryUsageTool(),
        GetDiskUsageTool(),
        GetSwapUsageTool(),
        GetSystemMetricsTool(),
        GetProcessesTool(),
        GetProcessMemoryTool(),
        QueryLogsTool(),
        GetPm2StatusTool(),
        GetPm2LogsTool(),
        GetMysqlStatusTool(),
        GetNginxStatusTool(),
        GetEc2StatusTool(),
        HealthCheckTool(),
    ]


def build_monitoring_tools() -> list[BaseTool]:
    return [
        GetCloudWatchAlarmTool(),
        GetCloudWatchMetricTool(),
        GetCpuUsageTool(),
        GetMemoryUsageTool(),
        GetDiskUsageTool(),
        GetSwapUsageTool(),
        GetSystemMetricsTool(),
        HealthCheckTool(),
    ]


def build_log_tools() -> list[BaseTool]:
    return [QueryLogsTool(), GetPm2LogsTool()]


def build_infra_tools() -> list[BaseTool]:
    return [
        GetEc2StatusTool(),
        GetNginxStatusTool(),
        GetPm2StatusTool(),
        GetProcessesTool(),
        GetProcessMemoryTool(),
        GetSystemMetricsTool(),
    ]


def build_database_tools() -> list[BaseTool]:
    return [GetMysqlStatusTool(), QueryLogsTool()]


def build_action_tools() -> list[BaseTool]:
    return [
        RestartPm2ProcessTool(),
        ClearTempFilesTool(),
        RotateLogsTool(),
        RestartMysqlTool(),
        ScaleEc2Tool(),
        ChangeConfigurationTool(),
    ]


def build_report_tools() -> list[BaseTool]:
    return [CreateIncidentReportTool()]


def execute_action_tool(tool_name: str, parameters: dict[str, Any] | None) -> str:
    """Execute an allowlisted write tool by name (policy must already have approved)."""
    parameters = parameters or {}
    if tool_name == "restart_pm2_process":
        return RestartPm2ProcessTool()._run(
            process_name=str(parameters.get("process_name", "api"))
        )
    if tool_name == "clear_temp_files":
        return ClearTempFilesTool()._run()
    if tool_name == "rotate_logs":
        return RotateLogsTool()._run()
    if tool_name == "restart_mysql":
        return RestartMysqlTool()._run()
    if tool_name == "scale_ec2":
        return ScaleEc2Tool()._run(
            desired_capacity=int(parameters.get("desired_capacity", 2))
        )
    if tool_name == "change_configuration":
        return ChangeConfigurationTool()._run(
            key=str(parameters.get("key", "")),
            value=str(parameters.get("value", "")),
        )
    raise ValueError(f"No executor registered for tool '{tool_name}'")
