"""Settings storage (key/value) for the /admin dashboard + notification prefs."""

from __future__ import annotations

from ..db import _conn

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
}


def get_setting(key: str, default: str = "") -> str:
    with _conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    return str(row["value"]) if row else default


def set_setting(key: str, value: str) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )


def set_settings(values: dict[str, str]) -> None:
    with _conn() as conn:
        for key, value in values.items():
            if key in SETTING_KEYS:
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, str(value or "")),
                )


def all_settings() -> dict[str, str]:
    with _conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


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
