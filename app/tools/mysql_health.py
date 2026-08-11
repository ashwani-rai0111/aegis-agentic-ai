"""Pure helpers for MySQL health evaluation (mock + AWS)."""

from __future__ import annotations

from typing import Any


def connection_ratio(current: Any, maximum: Any) -> float | None:
    try:
        cur = float(current)
        mx = float(maximum)
    except (TypeError, ValueError):
        return None
    if mx <= 0:
        return None
    return cur / mx


def evaluate_instance_health(
    *,
    reachable: bool,
    service_active: bool,
    current_connections: int | None,
    max_connections: int | None,
    threads_running: int | None,
    conn_saturation_pct: float = 90.0,
    threads_running_warn: int = 50,
    db_ok: bool = True,
    error: str | None = None,
) -> dict[str, Any]:
    """Score a single MySQL endpoint / global instance."""
    reasons: list[str] = []
    if not service_active:
        reasons.append("mysqld service not active")
    if not reachable:
        reasons.append(error or "cannot connect to MySQL")
    if not db_ok:
        reasons.append(error or "database probe failed")

    ratio = connection_ratio(current_connections, max_connections)
    saturated = ratio is not None and ratio * 100 >= conn_saturation_pct
    if saturated:
        reasons.append(
            f"connections saturated "
            f"({current_connections}/{max_connections} >= {conn_saturation_pct:.0f}%)"
        )

    threads_hot = (
        threads_running is not None and int(threads_running) >= int(threads_running_warn)
    )
    if threads_hot:
        reasons.append(
            f"threads_running high ({threads_running} >= {threads_running_warn})"
        )

    healthy = not reasons
    severe = (not service_active) or (not reachable) or saturated or threads_hot
    if not healthy and not severe:
        # soft failure (e.g. one schema missing) still unhealthy but not restart-first
        severe = False

    status = "online" if healthy else ("unreachable" if not reachable else "degraded")
    return {
        "healthy": healthy,
        "severe": severe,
        "status": status,
        "reasons": reasons,
        "connection_ratio": round(ratio, 3) if ratio is not None else None,
    }


def merge_mysql_report(
    *,
    service: dict[str, Any],
    globals_: dict[str, Any],
    environments: dict[str, dict[str, Any]],
    conn_saturation_pct: float = 90.0,
    threads_running_warn: int = 50,
) -> dict[str, Any]:
    """Build the canonical mysql block used by agents + verification."""
    service_active = bool(service.get("healthy") or service.get("status") == "active")
    reachable = bool(globals_.get("reachable", True))
    current = globals_.get("current_connections")
    maximum = globals_.get("max_connections")
    threads = globals_.get("threads_running")

    env_healthy = all(bool(env.get("healthy", True)) for env in environments.values())
    env_errors = [
        f"{name}: {env.get('error')}"
        for name, env in environments.items()
        if not env.get("healthy", True) and env.get("error")
    ]

    scored = evaluate_instance_health(
        reachable=reachable,
        service_active=service_active,
        current_connections=int(current) if current is not None else None,
        max_connections=int(maximum) if maximum is not None else None,
        threads_running=int(threads) if threads is not None else None,
        conn_saturation_pct=conn_saturation_pct,
        threads_running_warn=threads_running_warn,
        db_ok=env_healthy,
        error="; ".join(env_errors) if env_errors else globals_.get("error"),
    )

    # Prefer production metrics at top-level for backward-compatible agents.
    prod = environments.get("production") or {}
    return {
        "status": scored["status"],
        "healthy": scored["healthy"] and env_healthy and service_active and reachable,
        "severe": scored["severe"] or (not service_active) or (not reachable),
        "reasons": scored["reasons"],
        "service": service,
        "production": environments.get("production", {}),
        "staging": environments.get("staging", {}),
        "current_connections": current,
        "max_connections": maximum,
        "threads_running": threads,
        "slow_queries": globals_.get("slow_queries"),
        "aborted_connects": globals_.get("aborted_connects"),
        "uptime_seconds": globals_.get("uptime_seconds"),
        "version": globals_.get("version"),
        "connection_ratio": scored["connection_ratio"],
        "primary_database": prod.get("database"),
        "last_error": globals_.get("error")
        or next(
            (env.get("error") for env in environments.values() if env.get("error")),
            None,
        ),
    }
