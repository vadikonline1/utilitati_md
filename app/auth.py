"""User authentication helpers (password hashing + session tokens)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3

from .config import DEFAULT_PASSWORD, DEFAULT_USERNAME, SECRET_KEY
from .db import _conn


def register(username: str, password: str) -> int:
    """Create a new user. Raises ValueError if the username already exists."""
    try:
        with _conn() as conn:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, _hash_password(password)),
            )
            return cur.lastrowid
    except sqlite3.IntegrityError:
        raise ValueError("Numele de utilizator este deja folosit.")


def username_exists(username: str) -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
    return row is not None


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
            "SELECT id FROM users WHERE username = ?", (DEFAULT_USERNAME,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (DEFAULT_USERNAME, _hash_password(DEFAULT_PASSWORD)),
            )


def authenticate(username: str, password: str) -> int | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
    if row is None or not _verify_password(password, row["password_hash"]):
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
