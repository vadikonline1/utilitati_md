"""Settings storage (key/value) for the /admin dashboard + notification prefs."""

from __future__ import annotations

from ..db import _conn
from . import crypto

# Defaults (hours between syncs; 'daily' = once per day).
DEFAULT_SYNC_HOURS = 24
DEFAULT_SYNC_MODE = "daily"

SETTING_KEYS = {
    "smtp_host",
    "smtp_port",
    "smtp_user",
    "smtp_pass",
    "smtp_from",
    "telegram_token",
    "telegram_botname",
    "sync_mode",   # 'daily' or 'interval'
    "sync_hours",  # int, used when sync_mode == 'interval'
    # Data-retention / cleanup policy (managed from /admin).
    "retention_enabled",   # '1' or '0'
    "inactive_months",     # months of no login before deleting a user
    "warn_days",           # comma-separated days-before-deletion to send warnings
    "invoice_months",      # delete invoices older than this many months
    "unconfirmed_hours",   # delete unconfirmed accounts older than this many hours
}

# Per-type, per-language email templates edited from /admin (message management).
MSG_TYPES = ("invite", "welcome", "reset", "inactive")
for _mt in MSG_TYPES:
    for _lg in ("ro", "ru", "en"):
        SETTING_KEYS.add(f"msg_{_mt}_subj_{_lg}")
        SETTING_KEYS.add(f"msg_{_mt}_body_{_lg}")

# Values that must be stored encrypted so a database leak cannot reveal them.
_SECRET_KEYS = {"smtp_user", "smtp_pass", "telegram_token"}


def _read_decrypted(raw: str) -> str:
    """Return the plaintext of a stored value, decrypting secrets when needed."""
    if raw and crypto.is_encrypted(raw):
        dec = crypto.decrypt(raw)
        return dec if dec is not None else raw
    return raw


def get_setting(key: str, default: str = "") -> str:
    with _conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    value = str(row["value"]) if row else default
    if key in _SECRET_KEYS:
        return _read_decrypted(value)
    return value


def set_setting(key: str, value: str) -> None:
    stored = str(value)
    if key in _SECRET_KEYS:
        stored = crypto.encrypt(value) or ""
    with _conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, stored),
        )


def set_settings(values: dict[str, str]) -> None:
    with _conn() as conn:
        for key, value in values.items():
            if key in SETTING_KEYS:
                stored = str(value or "") if key not in _SECRET_KEYS else (
                    crypto.encrypt(value) or ""
                )
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, stored),
                )


def all_settings() -> dict[str, str]:
    with _conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    out = {}
    for row in rows:
        key, value = row["key"], row["value"]
        out[key] = _read_decrypted(value) if key in _SECRET_KEYS else value
    return out


def get_sync_interval_hours() -> int:
    """Return how often background sync should run, in hours."""
    mode = get_setting("sync_mode", DEFAULT_SYNC_MODE)
    if mode == "daily":
        return 24
    try:
        return max(1, min(168, int(float(get_setting("sync_hours", "24")))))
    except (TypeError, ValueError):
        return DEFAULT_SYNC_HOURS


# --------------------------------------------------------------------------- #
# CSV list helpers (used for user notification prefs)
# --------------------------------------------------------------------------- #
def parse_csv_list(raw: str | None) -> list[str]:
    """Split a comma-separated string into cleaned, non-empty entries."""
    if not raw:
        return []
    items = []
    for part in str(raw).split(","):
        p = part.strip()
        if p:
            items.append(p)
    return items


# --------------------------------------------------------------------------- #
# Data-retention policy (configurable from /admin)
# --------------------------------------------------------------------------- #
def retention_enabled() -> bool:
    return get_setting("retention_enabled", "1") == "1"


def get_int_setting(key: str, default: int) -> int:
    try:
        return int(float(get_setting(key, str(default))) or default)
    except (TypeError, ValueError):
        return default


def inactive_months() -> int:
    return get_int_setting("inactive_months", 12)


def invoice_months() -> int:
    return get_int_setting("invoice_months", 24)


def unconfirmed_hours() -> int:
    return get_int_setting("unconfirmed_hours", 24)


def warn_days() -> list[int]:
    """Days-before-deletion at which to send an inactivity warning email."""
    out = []
    for part in parse_csv_list(get_setting("warn_days", "90,60,30")):
        try:
            out.append(max(1, int(float(part))))
        except (TypeError, ValueError):
            continue
    return sorted(set(out), reverse=True)


# --------------------------------------------------------------------------- #
# Email message templates (managed from /admin, per language)
# --------------------------------------------------------------------------- #
def get_msg_subject(msg_type: str, lang: str) -> str:
    return get_setting(f"msg_{msg_type}_subj_{lang}", "")


def get_msg_body(msg_type: str, lang: str) -> str:
    return get_setting(f"msg_{msg_type}_body_{lang}", "")


def set_msg_templates(msg_type: str, subjects: dict, bodies: dict) -> None:
    """Persist subject+body for a message type across all languages."""
    values = {}
    for lang in ("ro", "ru", "en"):
        values[f"msg_{msg_type}_subj_{lang}"] = subjects.get(lang, "")
        values[f"msg_{msg_type}_body_{lang}"] = bodies.get(lang, "")
    set_settings(values)


def msg_templates(msg_type: str) -> dict[str, dict[str, str]]:
    """Return {lang: {subj, body}} for a message type, for the admin editor."""
    return {
        lang: {
            "subj": get_msg_subject(msg_type, lang),
            "body": get_msg_body(msg_type, lang),
        }
        for lang in ("ro", "ru", "en")
    }

