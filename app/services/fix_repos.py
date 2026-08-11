"""Parse configured Code Fix repositories and build Cursor agent prompts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.config import Settings, get_settings

FixProfile = Literal["backend_deploy", "frontend_github_only"]

VALID_PROFILES = {"backend_deploy", "frontend_github_only"}


@dataclass(frozen=True)
class FixRepo:
    key: str
    url: str
    profile: FixProfile
    # Branch Cursor starts from (main for node-server; your feature branch for frontend)
    starting_branch: str

    @property
    def deploy_label(self) -> str:
        if self.profile == "backend_deploy":
            return f"Backup branch, then push fix directly to `{self.starting_branch}` → AWS staging"
        return (
            f"GitHub only — start from `{self.starting_branch}`, "
            "new fix branch + push (store builds manual)"
        )


def parse_fix_repos(raw: str | None = None) -> dict[str, FixRepo]:
    """Parse AEGIS_FIX_REPOS.

    Preferred (clear with branches):
      key|url|profile|starting_branch
      node-server|https://github.com/org/node-server|backend_deploy|main
      frontend|https://github.com/org/app|frontend_github_only|release/1.2

    Also supported (colon form):
      key:https://github.com/org/repo:profile:branch
    """
    settings = get_settings()
    default_branch = (settings.aegis_fix_base_branch or "main").strip()
    text = raw if raw is not None else (settings.aegis_fix_repos or "")
    repos: dict[str, FixRepo] = {}
    for part in text.split(","):
        item = part.strip()
        if not item:
            continue
        if "|" in item:
            pieces = [p.strip() for p in item.split("|")]
            if len(pieces) < 3:
                continue
            key, url, profile = pieces[0], pieces[1], pieces[2]
            branch = pieces[3] if len(pieces) >= 4 and pieces[3] else default_branch
        else:
            pieces = item.split(":")
            # key:https://host/path:profile[:branch]
            if len(pieces) < 3:
                continue
            key = pieces[0].strip()
            if pieces[-1].strip() in VALID_PROFILES:
                profile = pieces[-1].strip()
                branch = default_branch
                url = ":".join(pieces[1:-1]).strip()
            elif len(pieces) >= 4 and pieces[-2].strip() in VALID_PROFILES:
                profile = pieces[-2].strip()
                branch = pieces[-1].strip() or default_branch
                url = ":".join(pieces[1:-2]).strip()
            else:
                continue
        if not key or not url or profile not in VALID_PROFILES:
            continue
        if not branch:
            branch = "main" if profile == "backend_deploy" else default_branch
        repos[key] = FixRepo(
            key=key,
            url=url,
            profile=profile,  # type: ignore[arg-type]
            starting_branch=branch,
        )
    return repos


def list_fix_repos() -> list[FixRepo]:
    return list(parse_fix_repos().values())


def get_fix_repo(repo_key: str) -> FixRepo | None:
    return parse_fix_repos().get(repo_key)


def backup_branch_name(settings: Settings | None = None, when: date | None = None) -> str:
    settings = settings or get_settings()
    prefix = settings.aegis_fix_backup_prefix or "backup-"
    day = (when or date.today()).isoformat()
    return f"{prefix}{day}"


def fix_branch_name(job_id: str) -> str:
    short = (job_id or "job").replace("-", "")[:8]
    return f"aegis/fix-{short}"


def build_fix_prompt(
    *,
    repo: FixRepo,
    error_text: str,
    notes: str | None,
    backup_branch: str,
    fix_branch: str,
) -> str:
    base = repo.starting_branch
    notes_block = (notes or "").strip() or "(none)"

    if repo.profile == "backend_deploy":
        return f"""You are fixing a bug in the repository {repo.url}.

Profile: backend_deploy (node-server).
Deploy branch: {base} (push here to trigger GitHub → AWS staging).

Follow this git sequence EXACTLY (no force-push, no rewriting history):

1. Fetch and checkout `{base}`; pull latest.
2. Create a safety backup branch named `{backup_branch}` from the current tip of `{base}`.
   - If `{backup_branch}` already exists on the remote, use `{backup_branch}-2` (then -3, etc.).
   - Push the backup branch to origin.
3. Checkout `{base}` again and pull (same tip as before the fix).
4. Investigate and apply a MINIMAL fix for the reported error below directly on `{base}`.
5. Commit on `{base}` with a clear message (e.g. "fix: <short description>").
6. Push `{base}` to origin. Do NOT open a Pull Request.
7. In your final response, include:
   - BACKUP_BRANCH=...
   - FIX_BRANCH={base}
   - PR_URL=(none)
   - SUMMARY=...

Pushing `{base}` triggers the operator's existing staging deploy. Do NOT trigger AWS yourself.
Do NOT force-push `{base}`. Do NOT skip the backup step.

## Reported error / bug
{error_text.strip()}

## Extra notes from operator
{notes_block}
"""

    # frontend_github_only — no backup/PR required; push fix branch only
    return f"""You are fixing a bug in the repository {repo.url}.

Profile: frontend_github_only (mobile/app repo).
Operator starting branch: {base}

Follow this git sequence EXACTLY (no force-push):

1. Fetch and checkout `{base}`; pull latest.
2. Create and checkout a NEW branch named `{fix_branch}` from `{base}`.
3. Investigate and apply a MINIMAL fix for the reported error below.
4. Commit with a clear message (e.g. "fix: <short description>").
5. Push `{fix_branch}` to origin (GitHub). Do NOT open a PR unless needed for push.
6. Do NOT merge into `{base}` yourself. Do NOT deploy. Do NOT publish to Play/App Store.
7. In your final response, include:
   - BACKUP_BRANCH=(none)
   - FIX_BRANCH=...
   - PR_URL=(none or n/a)
   - SUMMARY=...

There is NO server deploy for this repo. Store builds are manual later.

## Reported error / bug
{error_text.strip()}

## Extra notes from operator
{notes_block}
"""
