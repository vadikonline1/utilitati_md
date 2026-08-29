"""Shared FastAPI dependencies (auth parsing)."""

from __future__ import annotations

from fastapi import Cookie, HTTPException, status

from .auth import is_usable_user, parse_session_token


def get_auth_token(session: str | None = Cookie(default=None)) -> int:
    user_id = parse_session_token(session or "")
    if user_id is None or not is_usable_user(user_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user_id


def optional_auth_token(session: str | None = Cookie(default=None)) -> int | None:
    user_id = parse_session_token(session or "")
    if user_id is None or not is_usable_user(user_id):
        return None
    return user_id
