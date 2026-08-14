from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.auth import expected_session_token, verify_login

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=200)
    password: str = Field(..., min_length=1, max_length=200)


class LoginResponse(BaseModel):
    token: str
    username: str


class SessionResponse(BaseModel):
    ok: bool
    username: str | None = None


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    token = verify_login(payload.username, payload.password)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return LoginResponse(token=token, username=payload.username.strip())


@router.get("/session", response_model=SessionResponse)
def session(
    authorization: Annotated[str | None, Header()] = None,
) -> SessionResponse:
    if not authorization or not authorization.lower().startswith("bearer "):
        return SessionResponse(ok=False)
    token = authorization.split(" ", 1)[1].strip()
    if not token or not secrets.compare_digest(token, expected_session_token()):
        return SessionResponse(ok=False)
    return SessionResponse(ok=True, username=get_settings().aegis_dashboard_username)
