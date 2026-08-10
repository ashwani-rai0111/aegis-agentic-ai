"""In-memory mock infrastructure state for local demos (no AWS required)."""

from __future__ import annotations

from copy import deepcopy
from threading import Lock
from typing import Any

SCENARIO_API_MEMORY_PRESSURE = "api_memory_pressure"
SCENARIO_MYSQL_RESTART_REQUIRED = "mysql_restart_required"

SUPPORTED_SCENARIOS = {
    SCENARIO_API_MEMORY_PRESSURE,
    SCENARIO_MYSQL_RESTART_REQUIRED,
}

_API_MEMORY_PRESSURE: dict[str, Any] = {
    "instance_id": "i-mock-aegis-001",
    "region": "us-east-1",
    "service": "production-api",
    "alarm": {
        "alarm_name": "prod-api-high-latency",
        "state": "ALARM",
        "reason": "p95 latency > 2000ms for 5 minutes",
        "metric": "TargetResponseTime",
    },
    "ec2": {
        "instance_id": "i-mock-aegis-001",
        "state": "running",
        "instance_type": "t3.large",
        "private_ip": "10.0.1.24",
        "status_checks": {"system": "ok", "instance": "ok"},
    },
    "metrics": {
        "cpu_utilization": 31.0,
        "memory_utilization": 92.0,
        "swap_utilization": 68.0,
        "disk_utilization": 48.0,
        "api_p95_latency_ms": 2450.0,
        "api_error_rate": 4.8,
    },
    "processes": [
        {"name": "mysqld", "pid": 1102, "memory_mb": 720, "cpu": 8.0},
        {"name": "node-server", "pid": 2044, "memory_mb": 1100, "cpu": 18.0},
        {"name": "next-server", "pid": 2210, "memory_mb": 180, "cpu": 3.0},
        {"name": "nginx", "pid": 884, "memory_mb": 42, "cpu": 1.0},
    ],
    "mysql": {
        "status": "online",
        "max_connections": 200,
        "current_connections": 12,
        "buffer_pool_mb": 512,
        "slow_queries_1h": 3,
        "threads_running": 2,
        "healthy": True,
    },
    "nginx": {
        "status": "active",
        "active_connections": 86,
        "requests_per_sec": 42,
        "upstream": "api",
        "healthy": True,
    },
    "pm2": {
        "processes": [
            {
                "name": "api",
                "status": "online",
                "restarts": 12,
                "memory_mb": 1100,
                "cpu": 18,
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
    "pm2_logs": {
        "api": [
            "WARN memory pressure detected in api process",
            "ERROR request timeout after 5000ms path=/checkout",
            "WARN GC pause 890ms",
            "ERROR heap out of memory near threshold",
        ],
        "worker": ["INFO worker idle"],
    },
    "logs": [
        "WARN memory pressure detected in api process",
        "ERROR request timeout after 5000ms path=/checkout",
        "WARN GC pause 890ms",
        "INFO mysql slow query threshold exceeded",
    ],
    "temp_files_mb": 420,
    "health": {
        "http_status": 503,
        "endpoint": "/health",
        "body": "degraded",
    },
    "remediated": False,
    "scenario": SCENARIO_API_MEMORY_PRESSURE,
}

_MYSQL_RESTART_REQUIRED: dict[str, Any] = {
    "instance_id": "i-mock-aegis-002",
    "region": "us-east-1",
    "service": "production-api",
    "alarm": {
        "alarm_name": "prod-mysql-connections",
        "state": "ALARM",
        "reason": "MySQL threads_running and connection errors elevated",
        "metric": "DatabaseConnections",
    },
    "ec2": {
        "instance_id": "i-mock-aegis-002",
        "state": "running",
        "instance_type": "t3.large",
        "private_ip": "10.0.1.31",
        "status_checks": {"system": "ok", "instance": "ok"},
    },
    "metrics": {
        "cpu_utilization": 55.0,
        "memory_utilization": 78.0,
        "swap_utilization": 22.0,
        "disk_utilization": 51.0,
        "api_p95_latency_ms": 3100.0,
        "api_error_rate": 12.5,
    },
    "processes": [
        {"name": "mysqld", "pid": 1102, "memory_mb": 2100, "cpu": 62.0},
        {"name": "node-server", "pid": 2044, "memory_mb": 280, "cpu": 6.0},
        {"name": "next-server", "pid": 2210, "memory_mb": 160, "cpu": 2.0},
        {"name": "nginx", "pid": 884, "memory_mb": 40, "cpu": 1.0},
    ],
    "mysql": {
        "status": "degraded",
        "max_connections": 200,
        "current_connections": 198,
        "buffer_pool_mb": 512,
        "slow_queries_1h": 240,
        "threads_running": 180,
        "healthy": False,
        "last_error": "Too many connections / thread pileup",
    },
    "nginx": {
        "status": "active",
        "active_connections": 210,
        "requests_per_sec": 18,
        "upstream": "api",
        "healthy": True,
    },
    "pm2": {
        "processes": [
            {
                "name": "api",
                "status": "online",
                "restarts": 1,
                "memory_mb": 280,
                "cpu": 6,
                "unhealthy": False,
            },
            {
                "name": "worker",
                "status": "online",
                "restarts": 0,
                "memory_mb": 190,
                "cpu": 2,
                "unhealthy": False,
            },
        ]
    },
    "pm2_logs": {
        "api": [
            "ERROR SequelizeConnectionError: connect ECONNREFUSED",
            "WARN retrying database connection",
        ],
        "worker": ["WARN job delayed due to DB lock wait"],
    },
    "logs": [
        "ERROR mysql: Too many connections",
        "ERROR api failed to acquire DB connection",
        "WARN connection pool exhausted",
    ],
    "temp_files_mb": 80,
    "health": {
        "http_status": 503,
        "endpoint": "/health",
        "body": "database_unavailable",
    },
    "remediated": False,
    "scenario": SCENARIO_MYSQL_RESTART_REQUIRED,
}

_SCENARIO_TEMPLATES = {
    SCENARIO_API_MEMORY_PRESSURE: _API_MEMORY_PRESSURE,
    SCENARIO_MYSQL_RESTART_REQUIRED: _MYSQL_RESTART_REQUIRED,
}

_RECOVERED_METRICS = {
    "cpu_utilization": 22.0,
    "memory_utilization": 42.0,
    "swap_utilization": 12.0,
    "disk_utilization": 48.0,
    "api_p95_latency_ms": 320.0,
    "api_error_rate": 0.2,
}


class MockInfrastructure:
    """Scenario-scoped mock AWS/host state keyed by incident_id."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._incidents: dict[str, dict[str, Any]] = {}

    def bootstrap(self, incident_id: str, scenario: str = SCENARIO_API_MEMORY_PRESSURE) -> None:
        if scenario not in _SCENARIO_TEMPLATES:
            raise ValueError(
                f"Unsupported mock scenario: {scenario}. "
                f"Supported: {sorted(SUPPORTED_SCENARIOS)}"
            )
        with self._lock:
            self._incidents[incident_id] = deepcopy(_SCENARIO_TEMPLATES[scenario])

    def get(self, incident_id: str) -> dict[str, Any]:
        with self._lock:
            if incident_id not in self._incidents:
                raise KeyError(f"Unknown incident mock state: {incident_id}")
            return deepcopy(self._incidents[incident_id])

    def _mark_recovered(self, state: dict[str, Any], note: str) -> None:
        state["metrics"].update(_RECOVERED_METRICS)
        state["alarm"]["state"] = "OK"
        state["alarm"]["reason"] = note
        state["health"] = {
            "http_status": 200,
            "endpoint": "/health",
            "body": "ok",
        }
        state["remediated"] = True

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

            # Mirror process table for node-server alias of api
            for proc in state["processes"]:
                if proc["name"] in {"node-server", process_name} or (
                    process_name == "api" and proc["name"] == "node-server"
                ):
                    proc["memory_mb"] = 240
                    proc["cpu"] = 4.0

            state["pm2_logs"].setdefault(process_name, [])
            state["pm2_logs"][process_name] = [
                f"INFO pm2 restarted process {process_name}",
                "INFO process online",
            ]
            state["logs"] = [
                f"INFO pm2 restarted process {process_name}",
                "INFO api healthcheck passed",
                "INFO p95 latency normalized",
            ]
            if state.get("scenario") == SCENARIO_API_MEMORY_PRESSURE:
                self._mark_recovered(
                    state, "latency returned below threshold after PM2 restart"
                )
            return {
                "success": True,
                "instance_id": state["instance_id"],
                "process_name": process_name,
                "message": f"Restarted PM2 process '{process_name}' via mock SSM",
            }

    def clear_temp_files(self, incident_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._incidents[incident_id]
            before = state.get("temp_files_mb", 0)
            state["temp_files_mb"] = 12
            state["logs"].insert(0, "INFO cleared temporary files under /tmp/aegis")
            return {
                "success": True,
                "freed_mb": max(before - 12, 0),
                "temp_files_mb": 12,
            }

    def rotate_logs(self, incident_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._incidents[incident_id]
            rotated = len(state.get("logs", []))
            state["logs"] = ["INFO log rotation completed"]
            return {"success": True, "rotated_lines": rotated}

    def restart_mysql(self, incident_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._incidents[incident_id]
            state["mysql"] = {
                "status": "online",
                "max_connections": 200,
                "current_connections": 18,
                "buffer_pool_mb": 512,
                "slow_queries_1h": 1,
                "threads_running": 2,
                "healthy": True,
            }
            for proc in state["processes"]:
                if proc["name"] == "mysqld":
                    proc["memory_mb"] = 640
                    proc["cpu"] = 9.0
            state["logs"] = [
                "INFO mysql service restarted",
                "INFO connection pool healthy",
                "INFO api database checks passing",
            ]
            self._mark_recovered(state, "database recovered after controlled MySQL restart")
            return {
                "success": True,
                "instance_id": state["instance_id"],
                "message": "Restarted MySQL via mock SSM (approval-gated action)",
            }

    def scale_ec2(self, incident_id: str, desired_capacity: int) -> dict[str, Any]:
        with self._lock:
            state = self._incidents[incident_id]
            state["ec2"]["desired_capacity"] = desired_capacity
            state["logs"].insert(
                0, f"INFO ASG desired capacity set to {desired_capacity} (mock)"
            )
            return {
                "success": True,
                "desired_capacity": desired_capacity,
                "message": "Scaled EC2 capacity via mock ASG API",
            }

    def change_configuration(
        self, incident_id: str, key: str, value: str
    ) -> dict[str, Any]:
        with self._lock:
            state = self._incidents[incident_id]
            cfg = state.setdefault("config_changes", {})
            cfg[key] = value
            state["logs"].insert(0, f"INFO config changed {key}={value} (mock)")
            return {"success": True, "key": key, "value": value}


mock_infra = MockInfrastructure()
