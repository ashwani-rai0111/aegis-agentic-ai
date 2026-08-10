"""In-memory mock infrastructure state for local demos (no AWS required)."""

from __future__ import annotations

from copy import deepcopy
from threading import Lock
from typing import Any

SCENARIO_API_MEMORY_PRESSURE = "api_memory_pressure"

_BASE_STATE: dict[str, Any] = {
    "instance_id": "i-mock-aegis-001",
    "service": "production-api",
    "alarm": {
        "alarm_name": "prod-api-high-latency",
        "state": "ALARM",
        "reason": "p95 latency > 2000ms for 5 minutes",
        "metric": "TargetResponseTime",
    },
    "metrics": {
        "cpu_utilization": 28.0,
        "memory_utilization": 91.5,
        "swap_utilization": 72.0,
        "disk_utilization": 48.0,
        "api_p95_latency_ms": 2450.0,
        "api_error_rate": 4.8,
        "mysql_memory_mb": 1800.0,
        "mysql_connections": 140,
    },
    "pm2": {
        "processes": [
            {
                "name": "api",
                "status": "online",
                "restarts": 7,
                "memory_mb": 820,
                "cpu": 12,
                "unhealthy": True,
            },
            {
                "name": "worker",
                "status": "online",
                "restarts": 0,
                "memory_mb": 210,
                "cpu": 3,
                "unhealthy": False,
            },
        ]
    },
    "logs": [
        "WARN memory pressure detected in api process",
        "ERROR request timeout after 5000ms path=/checkout",
        "WARN GC pause 890ms",
        "INFO mysql slow query threshold exceeded",
    ],
    "remediated": False,
}

_RECOVERED_METRICS = {
    "cpu_utilization": 22.0,
    "memory_utilization": 61.0,
    "swap_utilization": 18.0,
    "disk_utilization": 48.0,
    "api_p95_latency_ms": 320.0,
    "api_error_rate": 0.2,
    "mysql_memory_mb": 900.0,
    "mysql_connections": 55,
}


class MockInfrastructure:
    """Scenario-scoped mock AWS/host state keyed by incident_id."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._incidents: dict[str, dict[str, Any]] = {}

    def bootstrap(self, incident_id: str, scenario: str = SCENARIO_API_MEMORY_PRESSURE) -> None:
        if scenario != SCENARIO_API_MEMORY_PRESSURE:
            raise ValueError(f"Unsupported mock scenario: {scenario}")
        with self._lock:
            self._incidents[incident_id] = deepcopy(_BASE_STATE)

    def get(self, incident_id: str) -> dict[str, Any]:
        with self._lock:
            if incident_id not in self._incidents:
                raise KeyError(f"Unknown incident mock state: {incident_id}")
            return deepcopy(self._incidents[incident_id])

    def restart_pm2_process(self, incident_id: str, process_name: str) -> dict[str, Any]:
        with self._lock:
            state = self._incidents[incident_id]
            found = False
            for proc in state["pm2"]["processes"]:
                if proc["name"] == process_name:
                    proc["status"] = "online"
                    proc["restarts"] = int(proc["restarts"]) + 1
                    proc["memory_mb"] = 240
                    proc["cpu"] = 4
                    proc["unhealthy"] = False
                    found = True
            if not found:
                return {"success": False, "error": f"process not found: {process_name}"}

            state["metrics"].update(_RECOVERED_METRICS)
            state["alarm"]["state"] = "OK"
            state["alarm"]["reason"] = "latency returned below threshold after remediation"
            state["logs"] = [
                "INFO pm2 restarted process api",
                "INFO api healthcheck passed",
                "INFO p95 latency normalized",
            ]
            state["remediated"] = True
            return {
                "success": True,
                "instance_id": state["instance_id"],
                "process_name": process_name,
                "message": f"Restarted PM2 process '{process_name}' via mock SSM",
            }


mock_infra = MockInfrastructure()