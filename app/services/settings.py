"""Settings storage (key/value) for the /admin dashboard + notification prefs.

SMTP and Telegram credentials can be provided either through the /admin UI
(stored encrypted in the database) or from the process environment
(`utilitati.env`). When an environment variable is set it takes precedence, so
credentials are never baked into source control.
"""

from __future__ import annotations

import os

from ..db import _conn
from . import crypto

# Defaults (hours between syncs; 'daily' = once per day).
DEFAULT_SYNC_HOURS = 24
DEFAULT_SYNC_MODE = "daily"

# Secret display sentinel: the admin UI never shows real secret values.
MASKED = "••••••••"

# Settings that may be configured from the environment (replaces DB value when
# set). Env names match what should live in utilitati.env.
ENV_SETTING_MAP = {
    "smtp_host": "SMTP_HOST",
    "smtp_port": "SMTP_PORT",
    "smtp_user": "SMTP_USER",
    "smtp_pass": "SMTP_PASS",
    "smtp_from": "SMTP_FROM",
    "telegram_token": "TELEGRAM_TOKEN",
    "telegram_botname": "TELEGRAM_BOTNAME",
    "fcm_service_account": "FCM_SERVICE_ACCOUNT",
    "push_provider": "PUSH_PROVIDER",
}

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
    # SEO / company info (managed from /admin?tab=seo).
    "meta_default_title",       # fallback <title> / meta title
    "meta_default_description", # fallback meta description
    "meta_default_keywords",    # fallback meta keywords
    "google_verification",      # Google Search Console verification meta value
    "search_verification_html", # full <meta>/<link> codes for search engines (HTML)
    "header_html",              # custom HTML injected into <head>
    "footer_html",              # custom HTML injected before </body>
    "company_name",             # platform operator name (GDPR)
    "company_email",            # official email / GDPR requests
    "company_address",          # registered / juridical address
    # AdMob / Google Ads (managed from /admin?tab=ads; consumed by the app).
    "admob_enabled",                # '1'/'0' master switch for the mobile app
    "admob_app_id_android",         # AdMob App ID (Android)
    "admob_app_id_ios",             # AdMob App ID (iOS)
    "admob_banner_enabled",         # '1'/'0'
    "admob_banner_unit_android",    # Android banner ad unit id
    "admob_banner_unit_ios",        # iOS banner ad unit id
    "admob_interstitial_enabled",   # '1'/'0'
    "admob_interstitial_unit_android",
    "admob_interstitial_unit_ios",
    "admob_interstitial_interval",  # min minutes between interstitials
    "admob_rewarded_enabled",       # '1'/'0'
    "admob_rewarded_unit_android",
    "admob_rewarded_unit_ios",
    "admob_placements",             # comma-list of screens that may show ads
    "fcm_service_account",          # Google FCM service-account JSON (secret)
    "push_provider",                # 'expo' or 'fcm' (mobile token mode)
}

# Per-type, per-language email templates edited from /admin (message management).
MSG_TYPES = ("invite", "welcome", "reset", "inactive", "invoices", "unpaid")
for _mt in MSG_TYPES:
    for _lg in ("ro", "ru", "en"):
        SETTING_KEYS.add(f"msg_{_mt}_subj_{_lg}")
        SETTING_KEYS.add(f"msg_{_mt}_body_{_lg}")

# Values that must be stored encrypted so a database leak cannot reveal them.
_SECRET_KEYS = {"smtp_user", "smtp_pass", "telegram_token", "fcm_service_account"}


def _read_decrypted(raw: str) -> str:
    """Return the plaintext of a stored value, decrypting secrets when needed."""
    if raw and crypto.is_encrypted(raw):
        dec = crypto.decrypt(raw)
        return dec if dec is not None else raw
    return raw


def is_env_setting(key: str) -> bool:
    """True when the given setting key is provided via the environment."""
    env_name = ENV_SETTING_MAP.get(key)
    return bool(env_name and os.getenv(env_name) is not None)


def get_setting(key: str, default: str = "") -> str:
    # Environment configuration takes precedence over the database value, so
    # SMTP/Telegram credentials can be supplied without touching the database.
    env_name = ENV_SETTING_MAP.get(key)
    if env_name:
        env_value = os.getenv(env_name)
        if env_value is not None:
            return env_value
    with _conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    value = str(row["value"]) if row else default
    if key in _SECRET_KEYS:
        return _read_decrypted(value)
    return value


def get_push_provider() -> str:
    """Return the current push provider mode ('expo' or 'fcm', default 'fcm')."""
    mode = get_setting("push_provider", "fcm").strip().lower()
    return mode if mode in ("expo", "fcm") else "fcm"


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


def settings_with_prefix(prefix: str) -> dict[str, str]:
    """Return {suffix: value} for stored settings keys starting with `prefix`."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE key LIKE ?", (prefix + "%",)
        ).fetchall()
    return {r["key"][len(prefix):]: r["value"] for r in rows}


def delete_setting(key: str) -> None:
    """Remove a settings row entirely (used for placeholder overrides)."""
    with _conn() as conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (key,))


def all_settings() -> dict[str, str]:
    """Return every stored setting for the admin UI.

    Secret values (SMTP password / user, Telegram token) are never returned in
    plaintext: they are replaced with a masked sentinel when configured. Env
    values override DB values, and each env-provided key is flagged
    `_env_<key>` so the template can show it came from the environment.
    """
    with _conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    out = {}
    for row in rows:
        key, value = row["key"], row["value"]
        out[key] = _read_decrypted(value) if key in _SECRET_KEYS else value
    for key, env_name in ENV_SETTING_MAP.items():
        env_value = os.getenv(env_name)
        if env_value is not None:
            if key in _SECRET_KEYS:
                out[key] = MASKED
            else:
                out[key] = env_value
            out[f"_env_{key}"] = "1"
    for key in _SECRET_KEYS:
        if out.get(key):
            out[key] = MASKED
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
    return get_int_setting("unconfirmed_hours", 1)


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


def clear_msg_templates(msg_type: str) -> None:
    """Remove any custom templates for a type so built-in defaults are used again."""
    values = {}
    for lang in ("ro", "ru", "en"):
        values[f"msg_{msg_type}_subj_{lang}"] = ""
        values[f"msg_{msg_type}_body_{lang}"] = ""
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


# --------------------------------------------------------------------------- #
# AdMob / Google Ads configuration (served to the mobile app via /api/config)
# --------------------------------------------------------------------------- #
def _flag(value: str) -> bool:
    return str(value).strip() == "1"


def admob_placements() -> list[str]:
    """Screens/placements that are allowed to show ads (from /admin)."""
    return parse_csv_list(get_setting("admob_placements", ""))


def placement_allows_ads(placement: str) -> bool:
    """True when ads are globally enabled and the given placement is allowed."""
    if not _flag(get_setting("admob_enabled", "0")):
        return False
    return placement in admob_placements()


def admob_config() -> dict:
    """Server-driven AdMob config for the mobile app (consumed at startup).

    Only safe (non-secret) values are exposed. The app treats an empty
    unit id as 'not configured for this platform' and disables that format.
    """
    return {
        "enabled": _flag(get_setting("admob_enabled", "0")),
        "app_id_android": get_setting("admob_app_id_android", "").strip(),
        "app_id_ios": get_setting("admob_app_id_ios", "").strip(),
        "banner": {
            "enabled": _flag(get_setting("admob_banner_enabled", "0")),
            "unit_android": get_setting("admob_banner_unit_android", "").strip(),
            "unit_ios": get_setting("admob_banner_unit_ios", "").strip(),
        },
        "interstitial": {
            "enabled": _flag(get_setting("admob_interstitial_enabled", "0")),
            "unit_android": get_setting("admob_interstitial_unit_android", "").strip(),
            "unit_ios": get_setting("admob_interstitial_unit_ios", "").strip(),
            "interval_minutes": get_int_setting("admob_interstitial_interval", 5),
        },
        "rewarded": {
            "enabled": _flag(get_setting("admob_rewarded_enabled", "0")),
            "unit_android": get_setting("admob_rewarded_unit_android", "").strip(),
            "unit_ios": get_setting("admob_rewarded_unit_ios", "").strip(),
        },
        "placements": admob_placements(),
    }

