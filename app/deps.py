"""Shared FastAPI dependencies (auth parsing: cookie session OR bearer token)."""

from __future__ import annotations

from fastapi import Cookie, Header, HTTPException, status

from .auth import is_usable_user, parse_session_token


def _resolve_token(session: str, authorization: str) -> str:
    if session:
        return session
    # Mobile apps send the session token as `Authorization: Bearer <token>`.
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value:
            return value.strip()
    return ""


def get_auth_token(
    session: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
) -> int:
    user_id = parse_session_token(_resolve_token(session or "", authorization or ""))
    if user_id is None or not is_usable_user(user_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user_id


def optional_auth_token(
    session: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
) -> int | None:
    user_id = parse_session_token(_resolve_token(session or "", authorization or ""))
    if user_id is None or not is_usable_user(user_id):
        return None
    return user_id
