"""Run Cursor Cloud Agents for Code Fix jobs."""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.database.session import SessionLocal
from app.models.db import FixJob
from app.services.fix_repos import (
    backup_branch_name,
    build_fix_prompt,
    fix_branch_name,
    get_fix_repo,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_running = 0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _extract_meta(text: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for key in ("BACKUP_BRANCH", "FIX_BRANCH", "PR_URL", "SUMMARY"):
        match = re.search(rf"{key}\s*[:=]\s*(\S.+)", text or "", re.IGNORECASE)
        if match:
            meta[key.lower()] = match.group(1).strip().strip("`\"'")
    # PR URL heuristic
    if "pr_url" not in meta:
        pr = re.search(r"https://github\.com/[^\s]+/pull/\d+", text or "")
        if pr:
            meta["pr_url"] = pr.group(0)
    return meta


def count_active_jobs(db) -> int:
    return (
        db.query(FixJob)
        .filter(FixJob.status.in_(("queued", "running")))
        .count()
    )


def start_fix_job_async(job_id: str) -> None:
    thread = threading.Thread(
        target=_run_fix_job,
        args=(job_id,),
        name=f"aegis-fix-{job_id[:8]}",
        daemon=True,
    )
    thread.start()


def _run_fix_job(job_id: str) -> None:
    global _running
    settings = get_settings()
    with _lock:
        if _running >= max(1, int(settings.aegis_fix_max_concurrent or 1)):
            db = SessionLocal()
            try:
                job = db.get(FixJob, job_id)
                if job and job.status == "queued":
                    job.status = "failed"
                    job.error = "Another fix job is already running (max concurrent reached)"
                    job.completed_at = _utcnow()
                    db.commit()
            finally:
                db.close()
            return
        _running += 1

    db = SessionLocal()
    try:
        job = db.get(FixJob, job_id)
        if not job:
            return
        job.status = "running"
        job.updated_at = _utcnow()
        db.commit()

        repo = get_fix_repo(job.repo_key)
        if not repo:
            job.status = "failed"
            job.error = f"Unknown repo_key '{job.repo_key}'"
            job.completed_at = _utcnow()
            db.commit()
            return

        base = repo.starting_branch or settings.aegis_fix_base_branch or "main"
        backup = job.backup_branch or backup_branch_name(settings)
        fix_br = job.fix_branch or fix_branch_name(job.id)
        if repo.profile == "frontend_github_only":
            job.backup_branch = "(none)"
        else:
            job.backup_branch = backup
            job.fix_branch = base  # backend pushes directly to deploy branch
        if repo.profile == "frontend_github_only":
            job.fix_branch = fix_br
        prompt = build_fix_prompt(
            repo=repo,
            error_text=job.error_text,
            notes=job.notes,
            backup_branch=backup,
            fix_branch=fix_br,
        )
        job.prompt = prompt
        db.commit()

        if not (settings.cursor_api_key or "").strip():
            job.status = "failed"
            job.error = (
                "CURSOR_API_KEY is not set. Add it in .env from "
                "Cursor Dashboard → Integrations, then retry."
            )
            job.completed_at = _utcnow()
            db.commit()
            return

        result_payload = _invoke_cursor_cloud(
            api_key=settings.cursor_api_key.strip(),
            model=settings.aegis_fix_model or "composer-2.5",
            repo_url=repo.url,
            base_branch=base,
            prompt=prompt,
            auto_create_pr=False,
        )
        job.cursor_agent_id = result_payload.get("agent_id")
        job.cursor_run_id = result_payload.get("run_id")
        meta = _extract_meta(result_payload.get("text") or "")
        if meta.get("backup_branch"):
            job.backup_branch = meta["backup_branch"]
        if meta.get("fix_branch"):
            job.fix_branch = meta["fix_branch"]
        if meta.get("pr_url"):
            job.pr_url = meta["pr_url"]
        elif result_payload.get("pr_url"):
            job.pr_url = result_payload["pr_url"]

        if result_payload.get("status") == "finished":
            job.status = "succeeded"
            job.summary = meta.get("summary") or result_payload.get("text", "")[:2000]
            job.error = None
        else:
            job.status = "failed"
            job.error = (
                result_payload.get("error")
                or result_payload.get("text")
                or "Cursor agent run failed"
            )[:2000]
            job.summary = result_payload.get("text", "")[:2000] or None
        job.completed_at = _utcnow()
        job.updated_at = _utcnow()
        db.commit()
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("fix job %s failed", job_id)
        try:
            job = db.get(FixJob, job_id)
            if job:
                job.status = "failed"
                job.error = str(exc)[:2000]
                job.completed_at = _utcnow()
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
        with _lock:
            _running = max(0, _running - 1)


def _normalize_github_url(url: str) -> str:
    u = (url or "").strip()
    if u.endswith(".git"):
        u = u[:-4]
    return u


def _invoke_cursor_cloud(
    *,
    api_key: str,
    model: str,
    repo_url: str,
    base_branch: str,
    prompt: str,
    auto_create_pr: bool = True,
) -> dict[str, Any]:
    from cursor_sdk import Agent, CloudAgentOptions, CloudRepository, CursorAgentError

    clean_url = _normalize_github_url(repo_url)
    try:
        with Agent.create(
            api_key=api_key,
            model=model,
            name="aegis-code-fix",
            cloud=CloudAgentOptions(
                repos=[
                    CloudRepository(
                        url=clean_url,
                        starting_ref=base_branch,
                    )
                ],
                auto_create_pr=auto_create_pr,
                skip_reviewer_request=True,
            ),
        ) as agent:
            agent_id = getattr(agent, "agent_id", None) or getattr(
                agent, "agentId", None
            )
            run = agent.send(prompt)
            run_id = getattr(run, "id", None)
            result = run.wait()
            status = getattr(result, "status", None) or "error"
            text = getattr(result, "result", None) or getattr(result, "text", None) or ""
            if callable(text):
                try:
                    text = text()
                except Exception:
                    text = str(text)
            text = str(text or "")
            pr_url = None
            # Some SDK versions expose PR on result / agent info
            for attr in ("pr_url", "prUrl", "pull_request_url"):
                if hasattr(result, attr):
                    pr_url = getattr(result, attr)
                    break
            return {
                "status": "finished" if status == "finished" else str(status),
                "text": text,
                "agent_id": str(agent_id) if agent_id else None,
                "run_id": str(run_id) if run_id else None,
                "pr_url": pr_url,
                "error": None if status == "finished" else text[:500] or str(status),
            }
    except CursorAgentError as err:
        msg = err.message or str(err)
        hint = ""
        low = msg.lower()
        if "verify existence of branch" in low or "repository" in low:
            hint = (
                " Hint: branch exists on GitHub for your account, but Cursor Cloud "
                "often cannot see private org repos until the Cursor GitHub App is "
                "granted access to that organization (Signyards5). In GitHub → "
                "Settings → Applications → Cursor (or Org Settings → Third-party "
                "access), allow the repo/org, then retry."
            )
        return {
            "status": "error",
            "text": "",
            "agent_id": None,
            "run_id": None,
            "pr_url": None,
            "error": (
                f"Cursor startup failed: {msg} "
                f"(retryable={err.is_retryable}).{hint}"
            ),
        }
