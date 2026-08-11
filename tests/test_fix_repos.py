from datetime import date

from app.services.fix_repos import (
    FixRepo,
    backup_branch_name,
    build_fix_prompt,
    fix_branch_name,
    parse_fix_repos,
)


def test_parse_pipe_format_with_branches():
    raw = (
        "node-server|https://github.com/acme/node-server|backend_deploy|main,"
        "frontend|https://github.com/acme/app|frontend_github_only|release/1.2"
    )
    repos = parse_fix_repos(raw)
    assert repos["node-server"].starting_branch == "main"
    assert repos["node-server"].profile == "backend_deploy"
    assert repos["frontend"].starting_branch == "release/1.2"
    assert "GitHub only" in repos["frontend"].deploy_label


def test_parse_colon_format_with_branch():
    raw = "frontend:https://github.com/acme/app:frontend_github_only:feature/checkout"
    repos = parse_fix_repos(raw)
    assert repos["frontend"].url == "https://github.com/acme/app"
    assert repos["frontend"].starting_branch == "feature/checkout"


def test_backup_and_fix_branch_names():
    assert backup_branch_name(when=date(2026, 8, 11)) == "backup-2026-08-11"
    assert fix_branch_name("abcd1234-xxxx").startswith("aegis/fix-")


def test_backend_prompt_backup_then_push_main():
    backend = FixRepo(
        key="node-server",
        url="https://github.com/acme/node-server",
        profile="backend_deploy",
        starting_branch="main",
    )
    prompt = build_fix_prompt(
        repo=backend,
        error_text="TypeError: x is not a function",
        notes="checkout flow",
        backup_branch="backup-2026-08-11",
        fix_branch="aegis/fix-abcd1234",
    )
    assert "backup-2026-08-11" in prompt
    assert "Push `main`" in prompt or "Push `main` to origin" in prompt
    assert "Do NOT open a Pull Request" in prompt
    assert "open a Pull Request into" not in prompt
    assert "TypeError" in prompt


def test_frontend_prompt_push_only_from_given_branch():
    front = FixRepo(
        key="frontend",
        url="https://github.com/acme/app",
        profile="frontend_github_only",
        starting_branch="release/1.2",
    )
    fp = build_fix_prompt(
        repo=front,
        error_text="Render error",
        notes=None,
        backup_branch="backup-2026-08-11",
        fix_branch="aegis/fix-ffff",
    )
    assert "release/1.2" in fp
    assert "Push" in fp or "push" in fp
    assert "Do NOT merge" in fp
