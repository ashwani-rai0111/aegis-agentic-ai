from __future__ import annotations

import hashlib
import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from app.config import get_settings


def _session_token(username: str, password: str) -> str:
    material = f"{username.strip()}:{password}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def expected_session_token() -> str:
    settings = get_settings()
    return _session_token(
        settings.aegis_dashboard_username,
        settings.aegis_dashboard_password,
    )


def verify_login(username: str, password: str) -> str | None:
    settings = get_settings()
    user_ok = secrets.compare_digest(
        (username or "").strip(),
        (settings.aegis_dashboard_username or "").strip(),
    )
    pass_ok = secrets.compare_digest(
        password or "",
        settings.aegis_dashboard_password or "",
    )
    if not (user_ok and pass_ok):
        return None
    return expected_session_token()


def verify_fix_password(password: str) -> bool:
    settings = get_settings()
    return secrets.compare_digest(
        password or "",
        settings.aegis_fix_password or "",
    )


def require_session(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Login required")
    token = authorization.split(" ", 1)[1].strip()
    if not token or not secrets.compare_digest(token, expected_session_token()):
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return token


RequireSession = Annotated[str, Depends(require_session)]
