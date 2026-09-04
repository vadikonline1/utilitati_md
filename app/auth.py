"""User authentication helpers (password hashing + session tokens)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta

from .config import DEFAULT_PASSWORD, DEFAULT_USERNAME, SECRET_KEY, _first_token
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


def new_invitation_token(user_id: int) -> str | None:
    """Generate and store a fresh confirmation token for an unconfirmed user.

    Returns the new token, or None if the user does not exist / already confirmed.
    """
    token = secrets.token_urlsafe(32)
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE users SET confirm_token = ? WHERE id = ? AND confirm_token IS NOT NULL",
            (token, user_id),
        )
        if not cur.rowcount:
            return None
    return token


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
    new_password = new_password.strip()
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


def deactivate_user(user_id: int, days: int = 30) -> str:
    """Deactivate an account and schedule permanent deletion after `days`.

    Returns the scheduled deletion date as an ISO-8601 string. The account can
    not be used (login rejected) during the grace period; a maintenance job
    removes it (with all invoices) once the date is reached.
    """
    delete_after = (datetime.now() + timedelta(days=days)).isoformat()
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET deactivated = 1, delete_after = ? WHERE id = ?",
            (delete_after, user_id),
        )
    return delete_after


def cancel_deactivation(user_id: int) -> None:
    """Restore a deactivated account (usable again, deletion cancelled)."""
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET deactivated = 0, delete_after = NULL WHERE id = ?",
            (user_id,),
        )


def get_deletion_info(user_id: int) -> tuple[bool, str | None]:
    """Return (deactivated, delete_after ISO string) for a user."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT deactivated, delete_after FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if row is None:
        return False, None
    return bool(row["deactivated"]), row["delete_after"]


def user_state(username: str) -> dict | None:
    """Return {is_active, deactivated, delete_after} for the username, if any."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT is_active, deactivated, delete_after FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
    return dict(row) if row else None


def is_usable_user(user_id: int) -> bool:
    """True when the user exists, is confirmed and is not deactivated."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT is_active, deactivated FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return (
        row is not None and bool(row["is_active"]) and not bool(row["deactivated"])
    )


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


def list_users() -> list[dict]:
    """Return all users (for the admin Users tab), newest first."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT u.id, u.username, u.full_name, u.email, u.is_active, "
            "u.created_at, datetime(u.last_login) AS last_login, "
            "CASE WHEN u.confirm_token IS NOT NULL THEN 1 ELSE 0 END AS pending, "
            "IFNULL((SELECT COUNT(*) FROM device_tokens d "
            "         WHERE d.user_id = u.id), 0) AS device_count "
            "FROM users u ORDER BY u.id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def set_user_active(user_id: int, is_active: bool) -> None:
    """Enable / disable a user account (is_active 1 or 0)."""
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, user_id),
        )


def set_user_full_name(user_id: int, full_name: str) -> None:
    """Update the user's display full name (used as the default for utilities)."""
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET full_name = ? WHERE id = ?",
            (full_name.strip(), user_id),
        )


def change_password(user_id: int, old_password: str, new_password: str) -> bool:
    """Change a user's password, verifying the old one first."""
    old_password = old_password.strip()
    new_password = new_password.strip()
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


def verify_password(user_id: int, password: str) -> bool:
    """Check a user's current password without changing it."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if row is None:
        return False
    return _verify_password(password, row["password_hash"])


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
        if row is not None:
            if not row["is_active"]:
                conn.execute(
                    "UPDATE users SET is_active = 1 WHERE id = ?", (row["id"],)
                )
            return
        # If the env previously created a mangled account (e.g. UTILITATI_USERNAME
        # was accidentally set to "admin, administrator"), adopt that account under
        # the clean default username instead of leaving a second/broken account.
        users = conn.execute("SELECT id, username, is_active FROM users").fetchall()
        for u in users:
            if (
                u["username"] != DEFAULT_USERNAME
                and _first_token(u["username"], "") == DEFAULT_USERNAME
            ):
                conn.execute(
                    "UPDATE users SET username = ?, is_active = 1 WHERE id = ?",
                    (DEFAULT_USERNAME, u["id"]),
                )
                return
        conn.execute(
            "INSERT INTO users (username, password_hash, is_active) VALUES (?, ?, 1)",
            (DEFAULT_USERNAME, _hash_password(DEFAULT_PASSWORD)),
        )


def authenticate(username: str, password: str) -> int | None:
    username = username.strip()
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, password_hash, is_active, deactivated "
            "FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if row is None or not row["is_active"] or row["deactivated"]:
        return None
    if not _verify_password(password, row["password_hash"]):
        return None
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET last_login = datetime('now') WHERE id = ?", (row["id"],)
        )
    return row["id"]


def get_user_lang(user_id: int) -> str | None:
    """Return the user's preferred platform language code, or None if unset."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT lang FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    lang = (row["lang"] if row else "") or ""
    return lang if lang in ("ro", "ru", "en") else None


def set_user_lang(user_id: int, lang: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET lang = ? WHERE id = ?",
            (lang if lang in ("ro", "ru", "en") else "", user_id),
        )



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
