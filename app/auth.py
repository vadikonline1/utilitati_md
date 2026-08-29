"""User authentication helpers (password hashing + session tokens)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta

from .config import DEFAULT_PASSWORD, DEFAULT_USERNAME, SECRET_KEY
from .db import _conn


def register(
    username: str,
    password: str,
    full_name: str = "",
    email: str = "",
    is_active: int = 1,
) -> int:
    """Create a new user. Raises ValueError if the username already exists.

    The default flow is: create an inactive user with no usable password, then
    confirm the email and only then set a generated password (see create_invitation).
    """
    username = username.strip()
    if username_exists(username):
        raise ValueError("Acest nume de utilizator este deja folosit.")
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, full_name, email, is_active) "
            "VALUES (?, ?, ?, ?, ?)",
            (username, _hash_password(password), full_name.strip(), email.strip(), is_active),
        )
        return cur.lastrowid


def create_invitation(username: str, full_name: str, email: str) -> tuple[int, str]:
    """Create an inactive user and return (user_id, confirmation token).

    The user cannot log in until the email is confirmed. The confirmation token
    is emailed to the user; after confirming, a generated password is set and sent.
    """
    username = username.strip()
    if username_exists(username):
        raise ValueError("Acest nume de utilizator este deja folosit.")
    token = secrets.token_urlsafe(32)
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, full_name, email, is_active, confirm_token) "
            "VALUES (?, ?, ?, ?, 0, ?)",
            (username, _hash_password(secrets.token_urlsafe(24)), full_name.strip(), email.strip(), token),
        )
        return cur.lastrowid, token


def confirm_invitation(token: str) -> tuple[int, str] | None:
    """Confirm a user's email, setting a generated password.

    Returns (user_id, generated_password) or None if the token is invalid."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE confirm_token = ?", (token,)
        ).fetchone()
        if row is None:
            return None
        password = secrets.token_urlsafe(8)
        conn.execute(
            "UPDATE users SET is_active = 1, confirm_token = NULL, password_hash = ? "
            "WHERE id = ?",
            (_hash_password(password), row["id"]),
        )
    return row["id"], password


def set_password_for_user(user_id: int, new_password: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, reset_token = NULL, reset_token_exp = NULL "
            "WHERE id = ?",
            (_hash_password(new_password), user_id),
        )


def set_reset_token(user_id: int, ttl_hours: int = 1) -> str:
    """Create a short-lived password-reset token for a user."""
    token = secrets.token_urlsafe(32)
    exp = (datetime.now() + timedelta(hours=ttl_hours)).isoformat()
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET reset_token = ?, reset_token_exp = ? WHERE id = ?",
            (token, exp, user_id),
        )
    return token


def user_by_email(email: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, username, full_name FROM users WHERE email = ?", (email.strip(),)
        ).fetchone()
    return dict(row) if row else None


def resolve_reset_token(token: str) -> int | None:
    """Return the user id if the reset token is valid and not expired."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, reset_token_exp FROM users WHERE reset_token = ?", (token,)
        ).fetchone()
    if row is None:
        return None
    exp = row["reset_token_exp"]
    if exp:
        try:
            if datetime.fromisoformat(exp) < datetime.now():
                return None
        except ValueError:
            return None
    return row["id"]


def username_exists(username: str) -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
    return row is not None


def get_user(user_id: int) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, username, full_name, email, is_active, notification_emails, "
            "telegram_chat_ids FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def change_password(user_id: int, old_password: str, new_password: str) -> bool:
    """Change a user's password, verifying the old one first."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if row is None or not _verify_password(old_password, row["password_hash"]):
        return False
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (_hash_password(new_password), user_id),
        )
    return True


def _hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 100_000
    ).hex()
    return f"{salt}${digest}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(_hash_password(password, salt), stored)


def ensure_default_user() -> None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, is_active FROM users WHERE username = ?", (DEFAULT_USERNAME,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO users (username, password_hash, is_active) VALUES (?, ?, 1)",
                (DEFAULT_USERNAME, _hash_password(DEFAULT_PASSWORD)),
            )
        elif not row["is_active"]:
            conn.execute(
                "UPDATE users SET is_active = 1 WHERE id = ?", (row["id"],)
            )


def authenticate(username: str, password: str) -> int | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, password_hash, is_active FROM users WHERE username = ?", (username,)
        ).fetchone()
    if row is None or not row["is_active"]:
        return None
    if not _verify_password(password, row["password_hash"]):
        return None
    return row["id"]


def create_session_token(user_id: int) -> str:
    payload = f"{user_id}.{secrets.token_urlsafe(32)}"
    sig = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def parse_session_token(token: str) -> int | None:
    try:
        user_id_part, random_part, sig = token.split(".")
    except ValueError:
        return None
    payload = f"{user_id_part}.{random_part}"
    expected = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        return int(user_id_part)
    except ValueError:
        return None


def ensure_user_created() -> None:
    ensure_default_user()
