"""Helpers to pick allowlisted PM2 remediation targets from evidence + user text."""

from __future__ import annotations

from typing import Any


def is_pm2_unhealthy(proc: dict[str, Any]) -> bool:
    status = str(proc.get("status") or "").lower()
    return bool(proc.get("unhealthy")) or status not in {
        "online",
        "launching",
        "",
    }


def pick_pm2_restart_target(
    processes: list[dict[str, Any]],
    *,
    user_message: str | None,
    allowlist: set[str],
    only_if_unhealthy: bool = True,
) -> str | None:
    """Choose which PM2 process to restart.

    By default only returns a target when a process is actually unhealthy.
    Never restarts just because the user asked a status question.
    """
    procs = [p for p in processes if p.get("name") in allowlist]
    if not procs:
        return None

    msg = (user_message or "").lower()
    if any(k in msg for k in ("website", "signyn", "site", "frontend", "web")):
        preferred = [
            "signyn",
            "signyardsnext",
            "websites",
            "node-server",
            "api",
            "worker",
        ]
    elif any(k in msg for k in ("node-server", "node", "api", "backend", "server")):
        preferred = [
            "node-server",
            "signyn",
            "signyardsnext",
            "websites",
            "api",
            "worker",
        ]
    else:
        preferred = [
            "signyn",
            "signyardsnext",
            "websites",
            "node-server",
            "api",
            "worker",
        ]

    for name in preferred:
        for proc in procs:
            if proc.get("name") == name and is_pm2_unhealthy(proc):
                return name

    for proc in procs:
        if is_pm2_unhealthy(proc):
            return str(proc["name"])

    if only_if_unhealthy:
        return None

    for name in preferred:
        if any(p.get("name") == name for p in procs):
            return name
    return None
