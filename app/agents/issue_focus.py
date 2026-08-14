"""Detect what the user is actually asking about (site vs MySQL vs node-server)."""

from __future__ import annotations

from typing import Any, Literal

from app.agents.pm2_targets import is_pm2_unhealthy

DbFocus = Literal["staging", "production", "both"]
IssueFocus = Literal["database", "website", "node_server", "general"]

WEBSITE_PM2_NAMES = ("signyn", "signyardsnext", "websites")
NODE_PM2_NAMES = ("node-server", "api")


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


def mentions_node_server(message: str | None) -> bool:
    msg = (message or "").lower()
    if "node-server" in msg or "nodeserver" in msg:
        return True
    if "node server" in msg:
        return True
    # api/backend without website wording
    if any(k in msg for k in ("backend", " node", "node ", "api")):
        if not any(k in msg for k in ("website", "frontend", "signyn.com")):
            return True
    return False


def mentions_website(message: str | None) -> bool:
    msg = (message or "").lower()
    return any(
        k in msg
        for k in (
            "website",
            "web site",
            "signyn",
            "frontend",
            "landing",
            "homepage",
            "home page",
            "site ",
            " site",
            "signyn.com",
        )
    )


def classify_issue_focus(message: str | None) -> IssueFocus:
    """Pick the primary thing the operator asked about."""
    msg = (message or "").lower()
    db = mentions_database(message)
    node = mentions_node_server(message)
    site = mentions_website(message)

    # Explicit process / DB wins over vague "site" wording
    if node and ("node-server" in msg or "node server" in msg or "nodeserver" in msg):
        return "node_server"
    if db and not node:
        return "database"
    if node and not site:
        return "node_server"
    if site and not node:
        return "website"
    if node:
        return "node_server"
    if db:
        return "database"
    if site:
        return "website"
    return "general"


def database_focus(message: str | None) -> DbFocus:
    msg = (message or "").lower()
    wants_staging = any(k in msg for k in ("staging", "uat", "uatsignyards"))
    wants_prod = any(
        k in msg for k in ("production", "prod db", "prod database", "signyards")
    )
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


def _proc_line(proc: dict[str, Any]) -> str:
    name = proc.get("name") or "?"
    status = proc.get("status") or "unknown"
    mem = proc.get("memory_mb")
    cpu = proc.get("cpu")
    bits = [f"PM2 '{name}' status={status}"]
    if mem is not None:
        bits.append(f"memory={mem}MB")
    if cpu is not None:
        bits.append(f"cpu={cpu}%")
    if proc.get("restarts") is not None:
        bits.append(f"restarts={proc.get('restarts')}")
    return ", ".join(bits)


def summarize_pm2_for_question(
    processes: list[dict[str, Any]] | None,
    message: str | None,
    allowlist: set[str],
) -> dict[str, Any]:
    """
    Summarize PM2 for the process family the user asked about.

    For node-server questions this only evaluates node-server/api — not the website.
    """
    focus = classify_issue_focus(message)
    procs = [p for p in (processes or []) if p.get("name") in allowlist]

    if focus == "node_server":
        wanted = [n for n in NODE_PM2_NAMES if n in allowlist] or list(NODE_PM2_NAMES)
        label = "node-server"
    elif focus == "website":
        wanted = [n for n in WEBSITE_PM2_NAMES if n in allowlist] or list(
            WEBSITE_PM2_NAMES
        )
        label = "website PM2"
    else:
        wanted = sorted(allowlist) if allowlist else []
        label = "PM2 apps"

    matched = [p for p in procs if p.get("name") in wanted]
    # Preserve preferred order
    ordered: list[dict[str, Any]] = []
    for name in wanted:
        for p in matched:
            if p.get("name") == name and p not in ordered:
                ordered.append(p)

    missing = [n for n in wanted if not any(p.get("name") == n for p in ordered)]
    # For node-server focus, node-server itself missing is the critical signal
    primary_missing = False
    if focus == "node_server":
        primary_missing = not any(p.get("name") == "node-server" for p in ordered)
        if primary_missing and any(p.get("name") == "api" for p in ordered):
            primary_missing = False  # api alias present
    elif focus == "website":
        primary_missing = not any(
            p.get("name") in WEBSITE_PM2_NAMES for p in ordered
        )

    unhealthy = [p for p in ordered if is_pm2_unhealthy(p)]
    healthy = bool(ordered) and not unhealthy and not primary_missing

    if primary_missing and focus == "node_server":
        detail = (
            "PM2 process 'node-server' was not found on the instance "
            f"(looked for: {', '.join(wanted)}; "
            f"running allowlisted: "
            f"{', '.join(str(p.get('name')) for p in procs) or 'none'})"
        )
        root = "PM2 process 'node-server' is not running / not listed"
    elif primary_missing and focus == "website":
        detail = (
            "No website PM2 app (signyn/signyardsnext/websites) was found. "
            f"Running allowlisted: "
            f"{', '.join(str(p.get('name')) for p in procs) or 'none'}"
        )
        root = "Website PM2 process is not running / not listed"
    elif unhealthy:
        detail = "; ".join(_proc_line(p) for p in unhealthy)
        root = f"{label} unhealthy: {detail}"
    elif ordered:
        detail = "; ".join(_proc_line(p) for p in ordered)
        root = f"{label} looks healthy ({detail})"
    else:
        detail = "No matching PM2 processes found"
        root = f"{label} status unavailable"
        healthy = False

    restart_target = None
    if unhealthy:
        restart_target = str(unhealthy[0].get("name"))
    elif primary_missing and focus == "node_server":
        restart_target = "node-server"
    elif primary_missing and focus == "website":
        for n in WEBSITE_PM2_NAMES:
            if n in allowlist:
                restart_target = n
                break

    return {
        "focus": focus,
        "label": label,
        "wanted": wanted,
        "matched": ordered,
        "missing": missing,
        "healthy": healthy,
        "detail": detail,
        "root_cause": root,
        "restart_target": restart_target,
    }


def summarize_website_http(
    health_block: dict[str, Any] | None,
    *,
    fallback_endpoint: str | None = None,
) -> dict[str, Any]:
    health = (health_block or {}).get("health") or health_block or {}
    http_status = int(health.get("http_status") or 0)
    endpoint = health.get("endpoint") or fallback_endpoint or "(no health URL)"
    ok = bool(health.get("ok"))
    if "ok" not in health:
        ok = 200 <= http_status < 400 if http_status else False
    if http_status == 0 and not fallback_endpoint and not health.get("endpoint"):
        ok = True  # no URL configured — don't invent an outage
        detail = "No public healthcheck URL configured"
        root = detail
    elif ok:
        detail = f"HTTP {http_status} from {endpoint}"
        root = f"Website appears reachable ({detail})"
    else:
        detail = f"HTTP {http_status} from {endpoint}"
        root = f"Website appears down or unhealthy ({detail})"
    return {
        "healthy": ok,
        "http_status": http_status,
        "endpoint": endpoint,
        "detail": detail,
        "root_cause": root,
    }


def build_focused_live_answer(
    *,
    report: str,
    health_block: dict[str, Any] | None,
    processes: list[dict[str, Any]] | None,
    mysql_summary: dict[str, Any],
    allowlist: set[str],
    fallback_endpoint: str | None = None,
) -> dict[str, Any]:
    """
    Build question-specific summary/root_cause from live probes.

    Returns keys: focus, healthy, needs_remediation, summary, root_cause,
    detail, restart_target, observations (list of tuples).
    """
    focus = classify_issue_focus(report)
    http = summarize_website_http(
        health_block, fallback_endpoint=fallback_endpoint
    )
    pm2 = summarize_pm2_for_question(processes, report, allowlist)

    observations: list[tuple[str, str, str, dict[str, Any]]] = []

    if focus == "database":
        observations.append(
            ("mysql", "status", str(mysql_summary.get("detail")), mysql_summary)
        )
        return {
            "focus": focus,
            "healthy": bool(mysql_summary.get("healthy")),
            "needs_remediation": not bool(mysql_summary.get("healthy")),
            "summary": (
                f"Checked live MySQL for: {report[:280]!r}. "
                f"{mysql_summary.get('detail')}. "
                + (
                    "No remediation needed."
                    if mysql_summary.get("healthy")
                    else "Database problem detected."
                )
            ),
            "root_cause": mysql_summary.get("root_cause"),
            "detail": mysql_summary.get("detail"),
            "restart_target": None,
            "proposed_action": "restart_mysql"
            if not mysql_summary.get("healthy")
            else "",
            "observations": observations,
            "http": http,
            "pm2": pm2,
        }

    if focus == "node_server":
        observations.append(
            (
                "pm2",
                "node_server_status",
                str(pm2.get("detail")),
                {"matched": pm2.get("matched"), "wanted": pm2.get("wanted")},
            )
        )
        healthy = bool(pm2.get("healthy"))
        if healthy:
            summary = (
                f"Checked PM2 node-server for: {report[:280]!r}. "
                f"{pm2.get('detail')}. "
                "Website/MySQL were not used as the answer for this question."
            )
            root = pm2.get("root_cause")
        else:
            summary = (
                f"Checked PM2 node-server for: {report[:280]!r}. "
                f"{pm2.get('detail')}."
            )
            root = pm2.get("root_cause")
        return {
            "focus": focus,
            "healthy": healthy,
            "needs_remediation": not healthy,
            "summary": summary,
            "root_cause": root,
            "detail": pm2.get("detail"),
            "restart_target": pm2.get("restart_target") or "node-server",
            "proposed_action": "restart_pm2_process" if not healthy else "",
            "observations": observations,
            "http": http,
            "pm2": pm2,
        }

    if focus == "website":
        observations.append(
            (
                "http",
                "health_check",
                str(http.get("detail")),
                {
                    "http_status": http.get("http_status"),
                    "endpoint": http.get("endpoint"),
                },
            )
        )
        observations.append(
            (
                "pm2",
                "website_status",
                str(pm2.get("detail")),
                {"matched": pm2.get("matched"), "wanted": pm2.get("wanted")},
            )
        )
        healthy = bool(http.get("healthy")) and bool(pm2.get("healthy"))
        if healthy:
            root = (
                f"Signyn website looks healthy "
                f"({http.get('detail')}; {pm2.get('detail')})"
            )
            summary = (
                f"Checked website for: {report[:280]!r}. "
                f"{http.get('detail')}. {pm2.get('detail')}. No remediation needed."
            )
        elif not http.get("healthy"):
            root = http.get("root_cause")
            summary = (
                f"Checked website for: {report[:280]!r}. {http.get('detail')}. "
                f"PM2: {pm2.get('detail')}."
            )
        else:
            root = pm2.get("root_cause")
            summary = (
                f"Checked website for: {report[:280]!r}. "
                f"HTTP ok ({http.get('detail')}) but {pm2.get('detail')}."
            )
        return {
            "focus": focus,
            "healthy": healthy,
            "needs_remediation": not healthy,
            "summary": summary,
            "root_cause": root,
            "detail": f"{http.get('detail')}; {pm2.get('detail')}",
            "restart_target": pm2.get("restart_target") or "signyn",
            "proposed_action": "restart_pm2_process" if not healthy else "",
            "observations": observations,
            "http": http,
            "pm2": pm2,
        }

    # general — full stack snapshot (alarm-driven / vague reports)
    observations.append(
        ("http", "health_check", str(http.get("detail")), dict(http))
    )
    observations.append(("pm2", "status", str(pm2.get("detail")), {"pm2": pm2}))
    observations.append(
        ("mysql", "status", str(mysql_summary.get("detail")), mysql_summary)
    )
    healthy = (
        bool(http.get("healthy"))
        and bool(pm2.get("healthy"))
        and bool(mysql_summary.get("healthy"))
    )
    detail = (
        f"{http.get('detail')}; {pm2.get('detail')}; MySQL: {mysql_summary.get('detail')}"
    )
    if healthy:
        root = f"Stack appears healthy ({detail})"
        summary = (
            f"Checked live evidence for: {report[:280]!r}. {detail}. "
            "No remediation needed."
        )
    else:
        root = f"Problem detected in live checks ({detail})"
        summary = f"Checked live evidence for: {report[:280]!r}. {detail}."
    restart = pm2.get("restart_target")
    proposed = ""
    if not healthy:
        if not mysql_summary.get("healthy") and http.get("healthy") and pm2.get(
            "healthy"
        ):
            proposed = "restart_mysql"
        else:
            proposed = "restart_pm2_process"
    return {
        "focus": focus,
        "healthy": healthy,
        "needs_remediation": not healthy,
        "summary": summary,
        "root_cause": root,
        "detail": detail,
        "restart_target": restart or "signyn",
        "proposed_action": proposed,
        "observations": observations,
        "http": http,
        "pm2": pm2,
    }
