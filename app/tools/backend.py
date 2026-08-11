"""Select mock vs AWS tool backend per incident."""

from __future__ import annotations

from typing import Any, Protocol

from app.config import get_settings
from app.tools.aws_backend import aws_backend
from app.tools.context import require_incident_id
from app.tools.mock_state import mock_infra


class ToolBackend(Protocol):
    def snapshot(self) -> dict[str, Any]: ...

    def get_cloudwatch_alarm(self, alarm_name: str) -> dict[str, Any]: ...

    def get_cloudwatch_metric(
        self, metric: str, period: int = 300, statistic: str = "Average"
    ) -> dict[str, Any]: ...

    def get_cpu_usage(self, note: str = "") -> dict[str, Any]: ...

    def get_memory_usage(self, note: str = "") -> dict[str, Any]: ...

    def get_disk_usage(self, note: str = "") -> dict[str, Any]: ...

    def get_swap_usage(self, note: str = "") -> dict[str, Any]: ...

    def get_system_metrics(self, note: str = "") -> dict[str, Any]: ...

    def get_processes(self, note: str = "") -> dict[str, Any]: ...

    def query_logs(
        self, service: str, time_range_minutes: int = 30, filter: str = ""
    ) -> dict[str, Any]: ...

    def get_pm2_status(self, note: str = "") -> dict[str, Any]: ...

    def get_pm2_logs(self, process_name: str) -> dict[str, Any]: ...

    def get_mysql_status(self, note: str = "") -> dict[str, Any]: ...

    def get_nginx_status(self, note: str = "") -> dict[str, Any]: ...

    def get_ec2_status(self, note: str = "") -> dict[str, Any]: ...

    def health_check(self, note: str = "") -> dict[str, Any]: ...

    def restart_pm2_process(self, process_name: str) -> dict[str, Any]: ...

    def clear_temp_files(self) -> dict[str, Any]: ...

    def rotate_logs(self) -> dict[str, Any]: ...

    def restart_mysql(self) -> dict[str, Any]: ...

    def scale_ec2(self, desired_capacity: int) -> dict[str, Any]: ...

    def change_configuration(self, key: str, value: str) -> dict[str, Any]: ...


class MockBackend:
    def __init__(self, incident_id: str) -> None:
        self.incident_id = incident_id

    def snapshot(self) -> dict[str, Any]:
        return mock_infra.get(self.incident_id)

    def get_cloudwatch_alarm(self, alarm_name: str) -> dict[str, Any]:
        alarm = self.snapshot()["alarm"]
        return {
            "requested_alarm": alarm_name,
            "alarm_name": alarm["alarm_name"],
            "state": alarm["state"],
            "reason": alarm["reason"],
            "metric": alarm["metric"],
        }

    def get_cloudwatch_metric(
        self, metric: str, period: int = 300, statistic: str = "Average"
    ) -> dict[str, Any]:
        state = self.snapshot()
        value = state["metrics"].get(metric)
        return {
            "metric": metric,
            "period": period,
            "statistic": statistic,
            "value": value,
            "unit": "Percent" if "utilization" in metric else "Count",
            "available_metrics": list(state["metrics"].keys()),
        }

    def get_cpu_usage(self, note: str = "") -> dict[str, Any]:
        return {
            "cpu_utilization": self.snapshot()["metrics"]["cpu_utilization"],
            "note": note,
        }

    def get_memory_usage(self, note: str = "") -> dict[str, Any]:
        return {
            "memory_utilization": self.snapshot()["metrics"]["memory_utilization"],
            "note": note,
        }

    def get_disk_usage(self, note: str = "") -> dict[str, Any]:
        return {
            "disk_utilization": self.snapshot()["metrics"]["disk_utilization"],
            "note": note,
        }

    def get_swap_usage(self, note: str = "") -> dict[str, Any]:
        return {
            "swap_utilization": self.snapshot()["metrics"]["swap_utilization"],
            "note": note,
        }

    def get_system_metrics(self, note: str = "") -> dict[str, Any]:
        state = self.snapshot()
        return {
            "instance_id": state["instance_id"],
            "metrics": state["metrics"],
            "temp_files_mb": state.get("temp_files_mb"),
            "remediated": state["remediated"],
            "note": note,
        }

    def get_processes(self, note: str = "") -> dict[str, Any]:
        processes = sorted(
            self.snapshot()["processes"],
            key=lambda p: p.get("memory_mb", 0),
            reverse=True,
        )
        return {"processes": processes, "note": note}

    def query_logs(
        self, service: str, time_range_minutes: int = 30, filter: str = ""
    ) -> dict[str, Any]:
        lines = self.snapshot()["logs"]
        if filter:
            lines = [line for line in lines if filter.lower() in line.lower()]
        return {
            "service": service,
            "time_range_minutes": time_range_minutes,
            "filter": filter,
            "lines": lines,
        }

    def get_pm2_status(self, note: str = "") -> dict[str, Any]:
        state = self.snapshot()
        return {
            "instance_id": state["instance_id"],
            "processes": state["pm2"]["processes"],
            "note": note,
        }

    def get_pm2_logs(self, process_name: str) -> dict[str, Any]:
        lines = self.snapshot().get("pm2_logs", {}).get(process_name, [])
        return {"process_name": process_name, "lines": lines}

    def get_mysql_status(self, note: str = "") -> dict[str, Any]:
        return {"mysql": self.snapshot()["mysql"], "note": note}

    def get_nginx_status(self, note: str = "") -> dict[str, Any]:
        return {"nginx": self.snapshot()["nginx"], "note": note}

    def get_ec2_status(self, note: str = "") -> dict[str, Any]:
        state = self.snapshot()
        return {"ec2": state["ec2"], "region": state.get("region"), "note": note}

    def health_check(self, note: str = "") -> dict[str, Any]:
        health = self.snapshot()["health"]
        status = int(health.get("http_status") or 0)
        return {
            "health": {
                **health,
                "ok": 200 <= status < 400,
            },
            "note": note,
        }

    def restart_pm2_process(self, process_name: str) -> dict[str, Any]:
        return mock_infra.restart_pm2_process(self.incident_id, process_name)

    def clear_temp_files(self) -> dict[str, Any]:
        return mock_infra.clear_temp_files(self.incident_id)

    def rotate_logs(self) -> dict[str, Any]:
        return mock_infra.rotate_logs(self.incident_id)

    def restart_mysql(self) -> dict[str, Any]:
        return mock_infra.restart_mysql(self.incident_id)

    def scale_ec2(self, desired_capacity: int) -> dict[str, Any]:
        return mock_infra.scale_ec2(self.incident_id, desired_capacity)

    def change_configuration(self, key: str, value: str) -> dict[str, Any]:
        return mock_infra.change_configuration(self.incident_id, key, value)


def resolve_tool_backend_name(incident_id: str | None = None) -> str:
    """mock if incident has mock state; else configured backend (default mock)."""
    if incident_id and mock_infra.has(incident_id):
        return "mock"
    backend = (get_settings().aegis_tool_backend or "mock").lower()
    return backend if backend in {"mock", "aws"} else "mock"


def aws_settings_ready() -> bool:
    settings = get_settings()
    return bool(
        settings.aws_access_key_id
        and settings.aws_secret_access_key
        and settings.aegis_ec2_instance_id
    )


def get_tool_backend(incident_id: str | None = None) -> ToolBackend:
    incident_id = incident_id or require_incident_id()
    if mock_infra.has(incident_id):
        return MockBackend(incident_id)
    settings = get_settings()
    if (settings.aegis_tool_backend or "").lower() != "aws":
        raise RuntimeError(
            "This incident has no mock state. Set AEGIS_TOOL_BACKEND=aws and configure "
            "AWS credentials for live incidents (or use POST /incidents/simulate)."
        )
    if not aws_settings_ready():
        raise RuntimeError(
            "AWS backend selected but missing AWS_ACCESS_KEY_ID, "
            "AWS_SECRET_ACCESS_KEY, or AEGIS_EC2_INSTANCE_ID"
        )
    return aws_backend
