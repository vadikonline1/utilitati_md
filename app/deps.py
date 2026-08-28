"""Shared FastAPI dependencies (auth parsing)."""

from __future__ import annotations

from fastapi import Cookie, HTTPException, status

from .auth import parse_session_token


def get_auth_token(session: str | None = Cookie(default=None)) -> int:
    user_id = parse_session_token(session or "")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user_id


def optional_auth_token(session: str | None = Cookie(default=None)) -> int | None:
    return parse_session_token(session or "")
