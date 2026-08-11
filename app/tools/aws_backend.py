"""AWS-backed implementations for Aegis ops tools (CloudWatch / EC2 / SSM)."""

from __future__ import annotations

import base64
import json
import re
import shlex
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from app.agents.pm2_targets import is_pm2_unhealthy
from app.config import get_settings
from app.tools import aws_clients
from app.tools.mysql_health import merge_mysql_report


# Logical metric name → (CloudWatch MetricName, prefer CWAgent namespace)
_METRIC_MAP: dict[str, tuple[str, str | None]] = {
    "cpu_utilization": ("cpu_usage_active", "AWS/EC2:CPUUtilization"),
    "memory_utilization": ("mem_used_percent", None),
    "swap_utilization": ("swap_used_percent", None),
    "disk_utilization": ("disk_used_percent", None),
    "api_p95_latency_ms": ("TargetResponseTime", "AWS/ApplicationELB"),
    "api_error_rate": ("HTTPCode_Target_5XX_Count", "AWS/ApplicationELB"),
}


class AwsBackend:
    """Live AWS operations for a configured EC2 + CloudWatch alarm."""

    def _pm2_shell(self, inner: str) -> list[str]:
        """Run a PM2 command as the app user with a real HOME/PM2_HOME."""
        settings = get_settings()
        pm2_bin = shlex.quote(settings.aegis_pm2_bin or "pm2")
        preferred = (settings.aegis_pm2_user or "").strip()
        preferred_q = shlex.quote(preferred) if preferred else ""
        inner_safe = inner.replace("'", "'\"'\"'")
        # Prefer configured user; else the first Linux user whose PM2_HOME has apps
        # (root before ubuntu — empty ubuntu ~/.pm2 was masking the real daemon).
        return [
            "set +e",
            f"PREFERRED_USER={preferred_q}",
            f"PM2_BIN={pm2_bin}",
            "pm2_count_for() {",
            "  user=\"$1\"; home=\"$2\"",
            "  sudo -u \"$user\" -H env HOME=\"$home\" PM2_HOME=\"$home/.pm2\" "
            "PATH=\"/usr/local/bin:/usr/bin:/bin\" "
            "bash -lc \"$PM2_BIN jlist\" 2>/dev/null "
            "| python3 -c 'import sys,json; "
            "d=json.load(sys.stdin); print(len(d))' 2>/dev/null || echo 0",
            "}",
            "pick_user() {",
            "  if [ -n \"$PREFERRED_USER\" ] && id \"$PREFERRED_USER\" >/dev/null 2>&1; then",
            "    home=$(getent passwd \"$PREFERRED_USER\" | cut -d: -f6)",
            "    [ -n \"$home\" ] || home=/home/$PREFERRED_USER",
            "    count=$(pm2_count_for \"$PREFERRED_USER\" \"$home\")",
            "    echo \"$PREFERRED_USER|$home|${count:-0}\"",
            "    return",
            "  fi",
            "  for user in root ubuntu ec2-user admin deploy; do",
            "    id \"$user\" >/dev/null 2>&1 || continue",
            "    home=$(getent passwd \"$user\" | cut -d: -f6)",
            "    [ -n \"$home\" ] || continue",
            "    count=$(pm2_count_for \"$user\" \"$home\")",
            "    if [ \"${count:-0}\" -gt 0 ]; then",
            "      echo \"$user|$home|$count\"",
            "      return",
            "    fi",
            "  done",
            "  if id root >/dev/null 2>&1; then echo \"root|/root|0\"; return; fi",
            "  echo \"ubuntu|/home/ubuntu|0\"",
            "}",
            "CHOSEN=$(pick_user)",
            "USER_NAME=$(echo \"$CHOSEN\" | cut -d'|' -f1)",
            "HOME_DIR=$(echo \"$CHOSEN\" | cut -d'|' -f2)",
            "COUNT=$(echo \"$CHOSEN\" | cut -d'|' -f3)",
            "echo \"AEGIS_PM2_USER=$USER_NAME\"",
            "echo \"AEGIS_PM2_HOME=$HOME_DIR/.pm2\"",
            "echo \"AEGIS_PM2_COUNT=$COUNT\"",
            (
                "sudo -u \"$USER_NAME\" -H env "
                f"HOME=\"$HOME_DIR\" PM2_HOME=\"$HOME_DIR/.pm2\" PM2_BIN={pm2_bin} "
                "PATH=\"$HOME_DIR/.local/bin:/usr/local/bin:/usr/bin:/bin:"
                "$HOME_DIR/.nvm/versions/node/$(ls \"$HOME_DIR/.nvm/versions/node\" 2>/dev/null | tail -n1)/bin:"
                "$PATH\" "
                f"bash -lc '{inner_safe}'"
            ),
        ]

    def _pm2_compact_inner(self) -> str:
        """Emit a small JSON array — full `pm2 jlist` is too large for SSM stdout."""
        # Write a tiny helper on the instance, then run it (avoids quoting hell).
        helper = (
            "import json\n"
            "d=json.load(open('/tmp/aegis_pm2_jlist.json'))\n"
            "out=[]\n"
            "for x in d:\n"
            " env=x.get('pm2_env') or {}\n"
            " monit=x.get('monit') or {}\n"
            " mem=monit.get('memory') or 0\n"
            " status=env.get('status')\n"
            " out.append({\n"
            "  'name': x.get('name'),\n"
            "  'status': status,\n"
            "  'restarts': env.get('restart_time', 0),\n"
            "  'memory_mb': round(float(mem)/(1024*1024), 1) if mem else 0,\n"
            "  'cpu': monit.get('cpu', 0),\n"
            "  'cwd': env.get('pm_cwd'),\n"
            "  'unhealthy': status not in ('online', 'launching'),\n"
            " })\n"
            "print(json.dumps(out))\n"
        )
        helper_b64 = base64.b64encode(helper.encode()).decode()
        return (
            f"echo {helper_b64} | base64 -d > /tmp/aegis_pm2_compact.py && "
            '"$PM2_BIN" jlist > /tmp/aegis_pm2_jlist.json && '
            "python3 /tmp/aegis_pm2_compact.py"
        )

    def _parse_pm2_jlist(self, stdout: str) -> list[dict[str, Any]]:
        text = (stdout or "").strip()
        lines = [
            ln
            for ln in text.splitlines()
            if not ln.startswith("AEGIS_PM2_") and ln.strip()
        ]
        payload = "\n".join(lines).strip() or "[]"
        start = payload.find("[")
        end = payload.rfind("]")
        if start >= 0 and end > start:
            payload = payload[start : end + 1]
        raw = json.loads(payload or "[]")
        processes: list[dict[str, Any]] = []
        for item in raw:
            # Compact exporter already shaped the fields
            if "pm2_env" not in item and "name" in item:
                status = item.get("status")
                processes.append(
                    {
                        "name": item.get("name"),
                        "status": status,
                        "restarts": item.get("restarts", 0),
                        "memory_mb": item.get("memory_mb", 0),
                        "cpu": item.get("cpu", 0),
                        "cwd": item.get("cwd"),
                        "unhealthy": bool(item.get("unhealthy"))
                        or status not in {"online", "launching"},
                    }
                )
                continue
            mem = item.get("monit", {}).get("memory", 0)
            status = item.get("pm2_env", {}).get("status")
            processes.append(
                {
                    "name": item.get("name"),
                    "status": status,
                    "restarts": item.get("pm2_env", {}).get("restart_time", 0),
                    "memory_mb": round(float(mem) / (1024 * 1024), 1) if mem else 0,
                    "cpu": item.get("monit", {}).get("cpu", 0),
                    "cwd": item.get("pm2_env", {}).get("pm_cwd"),
                    "unhealthy": status not in {"online", "launching"},
                }
            )
        return processes

    def _resolve_pm2_process_name(
        self, requested: str, processes: list[dict[str, Any]]
    ) -> str:
        names = [str(p.get("name")) for p in processes if p.get("name")]
        if requested in names:
            return requested
        req = requested.lower()
        aliases = {
            "websites": (
                "signyn",
                "signyardsnext",
                "website",
                "websites",
                "web",
                "frontend",
                "next",
            ),
            "website": ("signyn", "signyardsnext", "website", "websites", "next"),
            "signyn": ("signyn", "signyardsnext"),
            "node-server": ("node-server", "node", "api", "backend", "server"),
        }
        needles = aliases.get(req, (req,))
        # Prefer stopped/unhealthy matches first
        ranked = sorted(
            processes,
            key=lambda p: (0 if is_pm2_unhealthy(p) else 1, str(p.get("name"))),
        )
        for proc in ranked:
            name = str(proc.get("name") or "")
            lowered = name.lower()
            if any(n in lowered for n in needles):
                return name
        for proc in ranked:
            if proc.get("unhealthy") and proc.get("name"):
                return str(proc["name"])
        return requested

    def snapshot(self) -> dict[str, Any]:
        """Unified state shape used by verification."""
        settings = get_settings()
        alarm_name = settings.aegis_cw_alarm_name or "unknown"
        alarm = self.get_cloudwatch_alarm(alarm_name)
        metrics = self._collect_metrics()
        pm2 = self.get_pm2_status()
        health = self.health_check()
        ec2 = self.get_ec2_status()
        return {
            "instance_id": settings.aegis_ec2_instance_id,
            "region": settings.aws_region,
            "alarm": {
                "alarm_name": alarm.get("alarm_name", alarm_name),
                "state": alarm.get("state", "UNKNOWN"),
                "reason": alarm.get("reason", ""),
                "metric": alarm.get("metric"),
            },
            "metrics": metrics,
            "pm2": {"processes": pm2.get("processes", [])},
            "health": health.get("health", {}),
            "ec2": ec2.get("ec2", {}),
            "mysql": self.get_mysql_status().get("mysql")
            or {"healthy": True, "status": "unknown"},
            "remediated": False,
        }

    def get_cloudwatch_alarm(self, alarm_name: str) -> dict[str, Any]:
        settings = get_settings()
        name = alarm_name or settings.aegis_cw_alarm_name
        if not name:
            return {
                "requested_alarm": alarm_name,
                "alarm_name": alarm_name,
                "state": "NOT_CONFIGURED",
                "reason": "Set AEGIS_CW_ALARM_NAME in .env",
                "metric": None,
            }
        data = aws_clients.describe_alarm(name)
        data["requested_alarm"] = alarm_name
        return data

    def get_cloudwatch_metric(
        self, metric: str, period: int = 300, statistic: str = "Average"
    ) -> dict[str, Any]:
        value = self._resolve_metric(metric, period=period, statistic=statistic)
        return {
            "metric": metric,
            "period": period,
            "statistic": statistic,
            "value": value,
            "unit": "Percent" if "utilization" in metric else "Count",
            "available_metrics": list(_METRIC_MAP.keys())
            + ["cpu_utilization", "memory_utilization"],
            "source": "aws",
        }

    def get_cpu_usage(self, note: str = "") -> dict[str, Any]:
        return {
            "cpu_utilization": self._resolve_metric("cpu_utilization"),
            "note": note,
            "source": "aws",
        }

    def get_memory_usage(self, note: str = "") -> dict[str, Any]:
        return {
            "memory_utilization": self._resolve_metric("memory_utilization"),
            "note": note,
            "source": "aws",
        }

    def get_disk_usage(self, note: str = "") -> dict[str, Any]:
        return {
            "disk_utilization": self._resolve_metric("disk_utilization"),
            "note": note,
            "source": "aws",
        }

    def get_swap_usage(self, note: str = "") -> dict[str, Any]:
        return {
            "swap_utilization": self._resolve_metric("swap_utilization"),
            "note": note,
            "source": "aws",
        }

    def get_system_metrics(self, note: str = "") -> dict[str, Any]:
        settings = get_settings()
        # Prefer SSM for a single coherent host snapshot; fall back to CW.
        result = aws_clients.ssm_run(
            [
                "set -e",
                "MEM=$(free | awk '/Mem:/ {printf \"%.1f\", $3/$2*100}')",
                "SWAP=$(free | awk '/Swap:/ { if ($2>0) printf \"%.1f\", $3/$2*100; else print 0 }')",
                "DISK=$(df -P / | awk 'NR==2 {gsub(/%/,\"\",$5); print $5}')",
                "CPU=$(top -bn1 | awk -F'[, ]+' '/Cpu/ {print 100-$8; exit}')",
                'echo "{\\"memory_utilization\\": $MEM, \\"swap_utilization\\": $SWAP, '
                '\\"disk_utilization\\": $DISK, \\"cpu_utilization\\": $CPU}"',
            ]
        )
        metrics: dict[str, Any]
        if result.get("success") and result.get("stdout"):
            try:
                metrics = json.loads(result["stdout"].strip().splitlines()[-1])
            except json.JSONDecodeError:
                metrics = self._collect_metrics()
        else:
            metrics = self._collect_metrics()
            metrics["ssm_error"] = result.get("error")
        return {
            "instance_id": settings.aegis_ec2_instance_id,
            "metrics": metrics,
            "temp_files_mb": None,
            "remediated": False,
            "note": note,
            "source": "aws",
        }

    def get_processes(self, note: str = "") -> dict[str, Any]:
        result = aws_clients.ssm_run(
            [
                "ps -eo pid,comm,%cpu,rss --sort=-rss | head -n 15 "
                "| awk 'NR>1 {printf \"{\\\"pid\\\":%s,\\\"name\\\":\\\"%s\\\",\\\"cpu\\\":%s,\\\"memory_mb\\\":%.0f}\\n\", "
                "$1,$2,$3,$4/1024}' "
                '| awk \'BEGIN{print "["} {if(n++)printf ","; print} END{print "]"}\'',
            ]
        )
        processes: list[dict[str, Any]] = []
        if result.get("success") and result.get("stdout"):
            try:
                processes = json.loads(result["stdout"])
            except json.JSONDecodeError:
                processes = [{"raw": result["stdout"][:2000]}]
        else:
            return {
                "processes": [],
                "note": note,
                "error": result.get("error") or result.get("stderr"),
                "source": "aws",
            }
        return {"processes": processes, "note": note, "source": "aws"}

    def query_logs(
        self, service: str, time_range_minutes: int = 30, filter: str = ""
    ) -> dict[str, Any]:
        # Phase 1: pull recent journal/syslog via SSM (CloudWatch Logs can be added later).
        filt = filter.replace('"', "")
        cmd = (
            f"journalctl --no-pager -n 80 2>/dev/null || "
            f"tail -n 80 /var/log/syslog 2>/dev/null || "
            f"tail -n 80 /var/log/messages 2>/dev/null || true"
        )
        if filt:
            cmd = f"({cmd}) | grep -i {shlex.quote(filt)} || true"
        result = aws_clients.ssm_run([cmd])
        lines = [
            line for line in (result.get("stdout") or "").splitlines() if line.strip()
        ]
        return {
            "service": service,
            "time_range_minutes": time_range_minutes,
            "filter": filter,
            "lines": lines[:100],
            "source": "aws-ssm",
            "error": None if result.get("success") else result.get("error"),
        }

    def get_pm2_status(self, note: str = "") -> dict[str, Any]:
        settings = get_settings()
        result = aws_clients.ssm_run(
            self._pm2_shell(self._pm2_compact_inner())
        )
        meta_user = ""
        meta_home = ""
        for line in (result.get("stdout") or "").splitlines():
            if line.startswith("AEGIS_PM2_USER="):
                meta_user = line.split("=", 1)[1]
            if line.startswith("AEGIS_PM2_HOME="):
                meta_home = line.split("=", 1)[1]
        if result.get("success") and result.get("stdout"):
            try:
                processes = self._parse_pm2_jlist(result["stdout"])
            except json.JSONDecodeError:
                return {
                    "instance_id": settings.aegis_ec2_instance_id,
                    "processes": [],
                    "raw": (result.get("stdout") or "")[:2000],
                    "pm2_user": meta_user,
                    "pm2_home": meta_home,
                    "note": note,
                    "source": "aws",
                    "error": "Failed to parse pm2 jlist",
                }
        else:
            return {
                "instance_id": settings.aegis_ec2_instance_id,
                "processes": [],
                "pm2_user": meta_user,
                "pm2_home": meta_home,
                "note": note,
                "error": result.get("error") or result.get("stderr"),
                "source": "aws",
            }
        return {
            "instance_id": settings.aegis_ec2_instance_id,
            "processes": processes,
            "pm2_user": meta_user,
            "pm2_home": meta_home,
            "note": note,
            "source": "aws",
        }

    def get_pm2_logs(self, process_name: str) -> dict[str, Any]:
        settings = get_settings()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", process_name or ""):
            return {
                "process_name": process_name,
                "lines": [],
                "error": "Invalid process_name",
            }
        # Resolve alias against live process list when possible
        status = self.get_pm2_status()
        resolved = self._resolve_pm2_process_name(
            process_name, status.get("processes") or []
        )
        name = shlex.quote(resolved)
        result = aws_clients.ssm_run(
            self._pm2_shell(f'"$PM2_BIN" logs {name} --lines 40 --nostream --raw || true')
        )
        lines = [
            line
            for line in (result.get("stdout") or "").splitlines()
            if line.strip() and not line.startswith("AEGIS_PM2_")
        ]
        return {
            "process_name": resolved,
            "requested_process_name": process_name,
            "lines": lines[-80:],
            "pm2_user": status.get("pm2_user"),
            "source": "aws",
            "error": None if result.get("success") else result.get("error"),
        }

    def _mysql_cli_prefix(self) -> str:
        """Build a mysql client invocation that does not echo secrets in our meta lines."""
        settings = get_settings()
        host = shlex.quote(settings.aegis_mysql_host or "127.0.0.1")
        port = int(settings.aegis_mysql_port or 3306)
        user = (settings.aegis_mysql_user or "").strip()
        password = settings.aegis_mysql_password or ""
        if user:
            user_q = shlex.quote(user)
            # MYSQL_PWD avoids putting the password on argv; still keep scope local.
            pass_export = (
                f"export MYSQL_PWD={shlex.quote(password)}; "
                if password
                else ""
            )
            return (
                f"{pass_export}mysql -h{host} -P{port} -u{user_q} "
                "--batch --raw --skip-column-names"
            )
        # Local socket / root (SSM runs as root on this instance)
        return "mysql --batch --raw --skip-column-names"

    def get_mysql_status(self, note: str = "") -> dict[str, Any]:
        settings = get_settings()
        if not settings.aegis_mysql_enabled:
            return {
                "mysql": {
                    "status": "disabled",
                    "healthy": True,
                    "severe": False,
                    "message": "AEGIS_MYSQL_ENABLED=false",
                },
                "note": note,
                "source": "aws",
            }

        prod_db = (settings.aegis_mysql_prod_database or "").strip()
        staging_db = (settings.aegis_mysql_staging_database or "").strip()
        service_name = (settings.aegis_mysql_service_name or "mysql").strip()
        cli = self._mysql_cli_prefix()
        cfg = {
            "service_name": service_name,
            "cli": cli,
            "prod_db": prod_db,
            "staging_db": staging_db,
        }
        cfg_b64 = base64.b64encode(json.dumps(cfg).encode()).decode()

        helper = r'''import json, subprocess, base64, sys

cfg = json.loads(base64.b64decode(sys.argv[1]).decode())

def run(cmd):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()

service_name = cfg["service_name"]
rc, out, err = run("systemctl is-active %s 2>/dev/null || echo inactive" % service_name)
service_status = (out.splitlines() or ["inactive"])[0].strip() or "inactive"
service = {
    "name": service_name,
    "status": service_status,
    "healthy": service_status == "active",
}

cli = cfg["cli"]
globals_ = {
    "reachable": False,
    "current_connections": None,
    "max_connections": None,
    "threads_running": None,
    "slow_queries": None,
    "aborted_connects": None,
    "uptime_seconds": None,
    "version": None,
    "error": None,
}

sql = (
    "SHOW GLOBAL STATUS WHERE Variable_name IN "
    "('Threads_connected','Threads_running','Slow_queries','Aborted_connects','Uptime'); "
    "SHOW GLOBAL VARIABLES WHERE Variable_name IN ('max_connections','version');"
)
rc, out, err = run("%s -e %s" % (cli, json.dumps(sql)))
if rc == 0:
    globals_["reachable"] = True
    mapping = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            mapping[parts[0]] = parts[1]

    def as_int(key):
        try:
            return int(float(mapping.get(key) or 0))
        except Exception:
            return None

    globals_["current_connections"] = as_int("Threads_connected")
    globals_["threads_running"] = as_int("Threads_running")
    globals_["slow_queries"] = as_int("Slow_queries")
    globals_["aborted_connects"] = as_int("Aborted_connects")
    globals_["uptime_seconds"] = as_int("Uptime")
    globals_["max_connections"] = as_int("max_connections")
    globals_["version"] = mapping.get("version")
else:
    globals_["error"] = (err or out or "mysql client failed")[:400]


def probe_db(name):
    if not name:
        return {"database": name, "healthy": True, "skipped": True}
    rc, out, err = run("%s %s -e %s" % (cli, json.dumps(name), json.dumps("SELECT 1")))
    ok = rc == 0 and "1" in out.split()
    return {
        "database": name,
        "healthy": ok,
        "reachable": ok,
        "error": None if ok else (err or out or "probe failed")[:300],
    }

environments = {
    "production": probe_db(cfg.get("prod_db") or ""),
    "staging": probe_db(cfg.get("staging_db") or ""),
}
print(json.dumps({"service": service, "globals": globals_, "environments": environments}))
'''
        helper_b64 = base64.b64encode(helper.encode()).decode()
        result = aws_clients.ssm_run(
            [
                f"echo {helper_b64} | base64 -d > /tmp/aegis_mysql_check.py",
                f"python3 /tmp/aegis_mysql_check.py {cfg_b64}",
            ]
        )

        if not result.get("success") or not result.get("stdout"):
            return {
                "mysql": merge_mysql_report(
                    service={
                        "name": settings.aegis_mysql_service_name,
                        "status": "unknown",
                        "healthy": False,
                    },
                    globals_={
                        "reachable": False,
                        "error": result.get("error")
                        or result.get("stderr")
                        or "SSM mysql check failed",
                    },
                    environments={
                        "production": {
                            "database": prod_db,
                            "healthy": False,
                            "error": "check failed",
                        },
                        "staging": {
                            "database": staging_db,
                            "healthy": False,
                            "error": "check failed",
                        },
                    },
                    conn_saturation_pct=settings.aegis_mysql_conn_saturation_pct,
                    threads_running_warn=settings.aegis_mysql_threads_running_warn,
                ),
                "note": note,
                "source": "aws-ssm",
                "error": result.get("error") or result.get("stderr"),
            }

        try:
            lines = [
                ln
                for ln in (result.get("stdout") or "").splitlines()
                if ln.strip() and not ln.startswith("AEGIS_")
            ]
            payload = json.loads(lines[-1]) if lines else {}
        except json.JSONDecodeError:
            return {
                "mysql": {
                    "status": "degraded",
                    "healthy": False,
                    "severe": True,
                    "last_error": "Failed to parse mysql check JSON",
                    "raw": (result.get("stdout") or "")[:1000],
                },
                "note": note,
                "source": "aws-ssm",
            }

        mysql = merge_mysql_report(
            service=payload.get("service") or {},
            globals_=payload.get("globals") or {},
            environments=payload.get("environments") or {},
            conn_saturation_pct=settings.aegis_mysql_conn_saturation_pct,
            threads_running_warn=settings.aegis_mysql_threads_running_warn,
        )
        return {
            "mysql": mysql,
            "note": note,
            "source": "aws-ssm",
            "instance_id": settings.aegis_ec2_instance_id,
        }

    def get_nginx_status(self, note: str = "") -> dict[str, Any]:
        result = aws_clients.ssm_run(
            [
                "systemctl is-active nginx 2>/dev/null || "
                "service nginx status 2>/dev/null | head -n 1 || echo inactive"
            ]
        )
        status_line = (result.get("stdout") or "").strip().splitlines()
        status = status_line[0] if status_line else "unknown"
        return {
            "nginx": {
                "status": status,
                "healthy": status in {"active", "running"},
                "source": "aws-ssm",
            },
            "note": note,
        }

    def get_ec2_status(self, note: str = "") -> dict[str, Any]:
        settings = get_settings()
        instance_id = aws_clients.require_instance_id(settings)
        ec2 = aws_clients.describe_instance(instance_id)
        return {"ec2": ec2, "region": settings.aws_region, "note": note, "source": "aws"}

    def health_check(self, note: str = "") -> dict[str, Any]:
        settings = get_settings()
        url = settings.aegis_healthcheck_url
        if not url:
            return {
                "health": {
                    "http_status": 0,
                    "endpoint": None,
                    "body": "AEGIS_HEALTHCHECK_URL not set",
                    "ok": False,
                },
                "note": note,
                "source": "aws",
            }
        try:
            # Follow redirects; treat 2xx/3xx as healthy for public sites.
            with urlopen(url, timeout=15) as resp:  # noqa: S310 — operator-configured URL
                status = int(getattr(resp, "status", 200) or 200)
                body = resp.read(500).decode("utf-8", errors="replace")
                return {
                    "health": {
                        "http_status": status,
                        "endpoint": url,
                        "body": body,
                        "ok": 200 <= status < 400,
                    },
                    "note": note,
                    "source": "aws",
                }
        except HTTPError as exc:
            code = int(exc.code)
            return {
                "health": {
                    "http_status": code,
                    "endpoint": url,
                    "body": str(exc.reason),
                    "ok": 200 <= code < 400,
                },
                "note": note,
                "source": "aws",
            }
        except URLError as exc:
            return {
                "health": {
                    "http_status": 0,
                    "endpoint": url,
                    "body": str(exc.reason),
                    "ok": False,
                },
                "note": note,
                "source": "aws",
            }

    def restart_pm2_process(self, process_name: str) -> dict[str, Any]:
        settings = get_settings()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", process_name or ""):
            return {"success": False, "error": "Invalid process_name"}

        status = self.get_pm2_status()
        processes = status.get("processes") or []
        resolved = self._resolve_pm2_process_name(process_name, processes)
        available = [p.get("name") for p in processes if p.get("name")]

        if not processes:
            return {
                "success": False,
                "instance_id": settings.aegis_ec2_instance_id,
                "process_name": process_name,
                "resolved_process_name": resolved,
                "available_processes": available,
                "pm2_user": status.get("pm2_user"),
                "pm2_home": status.get("pm2_home"),
                "message": "No PM2 processes visible under the app user HOME",
                "error": status.get("error")
                or "PM2 process list empty — set AEGIS_PM2_USER to the Linux user that runs PM2",
                "source": "aws-ssm",
            }

        if resolved not in available:
            return {
                "success": False,
                "instance_id": settings.aegis_ec2_instance_id,
                "process_name": process_name,
                "resolved_process_name": resolved,
                "available_processes": available,
                "pm2_user": status.get("pm2_user"),
                "pm2_home": status.get("pm2_home"),
                "message": f"Process '{process_name}' not found in PM2",
                "error": f"Available PM2 apps: {available}",
                "source": "aws-ssm",
            }

        name = shlex.quote(resolved)
        result = aws_clients.ssm_run(
            self._pm2_shell(f'"$PM2_BIN" restart {name} --update-env')
        )
        # Confirm process is online after restart
        after = self.get_pm2_status()
        after_proc = next(
            (p for p in (after.get("processes") or []) if p.get("name") == resolved),
            None,
        )
        online = bool(
            after_proc
            and str(after_proc.get("status") or "").lower() in {"online", "launching"}
        )
        success = bool(result.get("success")) and online
        return {
            "success": success,
            "instance_id": settings.aegis_ec2_instance_id,
            "process_name": process_name,
            "resolved_process_name": resolved,
            "available_processes": available,
            "pm2_user": status.get("pm2_user") or after.get("pm2_user"),
            "pm2_home": status.get("pm2_home") or after.get("pm2_home"),
            "after_status": after_proc,
            "message": f"SSM pm2 restart '{resolved}' as user {status.get('pm2_user')}",
            "stdout": (result.get("stdout") or "")[:2000],
            "stderr": (result.get("stderr") or "")[:2000],
            "error": None
            if success
            else (result.get("error") or result.get("stderr") or "restart failed"),
            "source": "aws-ssm",
        }

    def clear_temp_files(self) -> dict[str, Any]:
        result = aws_clients.ssm_run(
            [
                "BEFORE=$(du -sm /tmp 2>/dev/null | awk '{print $1}')",
                "find /tmp -type f -mtime +1 -delete 2>/dev/null || true",
                "AFTER=$(du -sm /tmp 2>/dev/null | awk '{print $1}')",
                'echo "{\\"before_mb\\": $BEFORE, \\"after_mb\\": $AFTER}"',
            ]
        )
        payload: dict[str, Any] = {"success": bool(result.get("success"))}
        if result.get("stdout"):
            try:
                payload.update(json.loads(result["stdout"].strip().splitlines()[-1]))
            except json.JSONDecodeError:
                payload["raw"] = result["stdout"][:500]
        payload["error"] = result.get("error")
        payload["source"] = "aws-ssm"
        return payload

    def rotate_logs(self) -> dict[str, Any]:
        result = aws_clients.ssm_run(
            ["logrotate -f /etc/logrotate.conf 2>/dev/null || true; echo rotated"]
        )
        return {
            "success": bool(result.get("success")),
            "message": (result.get("stdout") or "").strip()[:200],
            "error": result.get("error"),
            "source": "aws-ssm",
        }

    def restart_mysql(self) -> dict[str, Any]:
        settings = get_settings()
        if not settings.aegis_mysql_restart_enabled:
            return {
                "success": False,
                "error": "AEGIS_MYSQL_RESTART_ENABLED=false",
                "source": "aws",
            }
        service = shlex.quote(settings.aegis_mysql_service_name or "mysql")
        result = aws_clients.ssm_run(
            [
                "set -e",
                f"systemctl restart {service}",
                "sleep 3",
                f"systemctl is-active {service}",
                "mysqladmin ping --silent || mysql -e 'SELECT 1' >/dev/null",
                'echo \'{"restarted": true}\'',
            ]
        )
        after = self.get_mysql_status()
        mysql = after.get("mysql") or {}
        success = bool(result.get("success")) and bool(mysql.get("healthy"))
        return {
            "success": success,
            "instance_id": settings.aegis_ec2_instance_id,
            "service": settings.aegis_mysql_service_name,
            "message": f"SSM systemctl restart {settings.aegis_mysql_service_name}",
            "stdout": (result.get("stdout") or "")[:500],
            "stderr": (result.get("stderr") or "")[:500],
            "mysql_after": {
                "healthy": mysql.get("healthy"),
                "status": mysql.get("status"),
                "production": mysql.get("production"),
                "staging": mysql.get("staging"),
                "current_connections": mysql.get("current_connections"),
                "threads_running": mysql.get("threads_running"),
            },
            "error": None
            if success
            else (result.get("error") or result.get("stderr") or "MySQL still unhealthy"),
            "source": "aws-ssm",
        }

    def scale_ec2(self, desired_capacity: int) -> dict[str, Any]:
        return {
            "success": False,
            "desired_capacity": desired_capacity,
            "error": "scale_ec2 is not enabled on AWS backend in phase 1",
            "source": "aws",
        }

    def change_configuration(self, key: str, value: str) -> dict[str, Any]:
        return {
            "success": False,
            "key": key,
            "value": value,
            "error": "change_configuration is not enabled on AWS backend in phase 1",
            "source": "aws",
        }

    def _collect_metrics(self) -> dict[str, Any]:
        return {
            "cpu_utilization": self._resolve_metric("cpu_utilization") or 0.0,
            "memory_utilization": self._resolve_metric("memory_utilization") or 0.0,
            "swap_utilization": self._resolve_metric("swap_utilization") or 0.0,
            "disk_utilization": self._resolve_metric("disk_utilization") or 0.0,
            "api_p95_latency_ms": self._resolve_metric("api_p95_latency_ms"),
            "api_error_rate": self._resolve_metric("api_error_rate"),
        }

    def _resolve_metric(
        self, metric: str, *, period: int = 300, statistic: str = "Average"
    ) -> float | None:
        settings = get_settings()
        instance_id = settings.aegis_ec2_instance_id
        dims = (
            [{"Name": "InstanceId", "Value": instance_id}] if instance_id else []
        )
        mapping = _METRIC_MAP.get(metric)
        if not mapping:
            # Treat unknown names as CWAgent metric names directly.
            return aws_clients.get_metric_statistic(
                namespace=settings.aegis_cw_namespace,
                metric_name=metric,
                dimensions=dims,
                period=period,
                statistic=statistic,
            )

        primary, fallback = mapping
        value = aws_clients.get_metric_statistic(
            namespace=settings.aegis_cw_namespace,
            metric_name=primary,
            dimensions=dims,
            period=period,
            statistic=statistic,
        )
        if value is not None:
            return value

        if fallback == "AWS/EC2:CPUUtilization":
            return aws_clients.get_metric_statistic(
                namespace="AWS/EC2",
                metric_name="CPUUtilization",
                dimensions=dims,
                period=period,
                statistic=statistic,
            )
        if fallback == "AWS/ApplicationELB":
            # Without target-group dimensions we cannot fetch ALB metrics reliably.
            return None
        return None


aws_backend = AwsBackend()
