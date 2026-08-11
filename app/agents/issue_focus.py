"""Detect what the user is actually asking about (site vs MySQL vs API)."""

from __future__ import annotations

from typing import Any, Literal

DbFocus = Literal["staging", "production", "both"]


def mentions_database(message: str | None) -> bool:
    msg = (message or "").lower()
    return any(
        k in msg
        for k in (
            "mysql",
            "database",
            "databases",
            "db ",
            " db",
            "sql",
            "staging db",
            "prod db",
            "uatsignyards",
            "signyards",
        )
    )


def database_focus(message: str | None) -> DbFocus:
    msg = (message or "").lower()
    wants_staging = any(k in msg for k in ("staging", "uat", "uatsignyards"))
    wants_prod = any(
        k in msg for k in ("production", "prod db", "prod database", "signyards")
    )
    # "is my staging database" → staging only
    if wants_staging and not wants_prod:
        return "staging"
    if wants_prod and not wants_staging:
        return "production"
    return "both"


def summarize_mysql_for_question(
    mysql_block: dict[str, Any] | None,
    message: str | None,
) -> dict[str, Any]:
    """Build a clear answer for DB-focused questions from get_mysql_status output."""
    block = mysql_block or {}
    focus = database_focus(message)
    service = block.get("service") or {}
    production = block.get("production") or {}
    staging = block.get("staging") or {}

    targets: list[tuple[str, dict[str, Any]]] = []
    if focus in {"staging", "both"}:
        targets.append(("staging", staging))
    if focus in {"production", "both"}:
        targets.append(("production", production))

    parts: list[str] = []
    all_ok = bool(block.get("healthy", True)) and bool(service.get("healthy", True))
    for label, env in targets:
        db_name = env.get("database") or label
        ok = bool(env.get("healthy", True))
        all_ok = all_ok and ok
        if ok:
            parts.append(f"{label} MySQL database '{db_name}' is reachable")
        else:
            err = env.get("error") or "probe failed"
            parts.append(f"{label} MySQL database '{db_name}' is NOT healthy ({err})")

    if service:
        svc_status = service.get("status") or "unknown"
        if service.get("healthy"):
            parts.append(f"mysqld service is {svc_status}")
        else:
            all_ok = False
            parts.append(f"mysqld service is {svc_status}")

    conns = block.get("current_connections")
    max_c = block.get("max_connections")
    threads = block.get("threads_running")
    if conns is not None and max_c is not None:
        parts.append(f"connections {conns}/{max_c}, threads_running={threads}")

    detail = "; ".join(parts) if parts else "MySQL status unavailable"
    if all_ok:
        root = (
            f"Staging MySQL looks healthy ({detail})"
            if focus == "staging"
            else f"Production MySQL looks healthy ({detail})"
            if focus == "production"
            else f"MySQL production/staging look healthy ({detail})"
        )
    else:
        root = (
            f"Staging MySQL problem detected ({detail})"
            if focus == "staging"
            else f"Production MySQL problem detected ({detail})"
            if focus == "production"
            else f"MySQL problem detected ({detail})"
        )

    return {
        "focus": focus,
        "healthy": all_ok,
        "severe": bool(block.get("severe")) or not all_ok,
        "detail": detail,
        "root_cause": root,
        "production": production,
        "staging": staging,
        "service": service,
    }
