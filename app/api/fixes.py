from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.session import get_db
from app.models.db import FixJob, utcnow
from app.models.schemas import (
    FixJobCreate,
    FixJobOut,
    FixRepoOut,
)
from app.services.auth import RequireSession, verify_fix_password
from app.services.cursor_fix import count_active_jobs, start_fix_job_async
from app.services.fix_repos import (
    backup_branch_name,
    fix_branch_name,
    get_fix_repo,
    list_fix_repos,
)

router = APIRouter(prefix="/fixes", tags=["fixes"])


@router.get("/repos", response_model=list[FixRepoOut])
def list_repos() -> list[FixRepoOut]:
    return [
        FixRepoOut(
            key=r.key,
            url=r.url,
            profile=r.profile,
            starting_branch=r.starting_branch,
            deploy_label=r.deploy_label,
        )
        for r in list_fix_repos()
    ]


@router.get("", response_model=list[FixJobOut])
def list_jobs(db: Session = Depends(get_db)) -> list[FixJobOut]:
    rows = db.query(FixJob).order_by(FixJob.created_at.desc()).limit(50).all()
    return [FixJobOut.model_validate(r) for r in rows]


@router.get("/{job_id}", response_model=FixJobOut)
def get_job(job_id: str, db: Session = Depends(get_db)) -> FixJobOut:
    job = db.get(FixJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Fix job not found")
    return FixJobOut.model_validate(job)


@router.post("", response_model=FixJobOut)
def create_job(
    payload: FixJobCreate,
    _: RequireSession,
    db: Session = Depends(get_db),
) -> FixJobOut:
    settings = get_settings()
    if not verify_fix_password(payload.fix_password):
        raise HTTPException(status_code=403, detail="Invalid fix password")
    repo = get_fix_repo(payload.repo_key)
    if not repo:
        configured = [r.key for r in list_fix_repos()]
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown repo_key '{payload.repo_key}'. "
                f"Configure AEGIS_FIX_REPOS. Known: {configured or '(none)'}"
            ),
        )

    active = count_active_jobs(db)
    if active >= max(1, int(settings.aegis_fix_max_concurrent or 1)):
        raise HTTPException(
            status_code=409,
            detail="A fix job is already queued/running. Wait for it to finish.",
        )

    job = FixJob(
        repo_key=repo.key,
        repo_url=repo.url,
        profile=repo.profile,
        status="queued",
        error_text=payload.error_text.strip(),
        notes=(payload.notes or "").strip() or None,
        backup_branch=backup_branch_name(settings),
        fix_branch="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    job.fix_branch = fix_branch_name(job.id)
    job.updated_at = utcnow()
    db.commit()
    db.refresh(job)

    start_fix_job_async(job.id)
    return FixJobOut.model_validate(job)
