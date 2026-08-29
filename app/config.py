"""Application configuration for Utilități Moldova website."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "app" / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
DB_PATH = Path(os.getenv("UTILITATI_DB", BASE_DIR / "utilitati.db"))

APP_NAME = "Utilități.MD"
SECRET_KEY = os.getenv("UTILITATI_SECRET_KEY", "change-me-in-production")
DEFAULT_USERNAME = os.getenv("UTILITATI_USERNAME", "admin")
DEFAULT_PASSWORD = os.getenv("UTILITATI_PASSWORD", "admin")
# Usernames granted access to the /admin dashboard. Comma-separated list, e.g.
# "admin,ion.popusoi,ion,ustroi". Set in utilitati.env (UTILITATI_ADMIN_USERNAME).
ADMIN_USERNAMES = {
    name.strip()
    for name in os.getenv(
        "UTILITATI_ADMIN_USERNAME", DEFAULT_USERNAME
    ).split(",")
    if name.strip()
}


def is_admin_username(username: str | None) -> bool:
    """True when the given username is in the comma-separated admin list."""
    return username in ADMIN_USERNAMES
# Public base URL used to build invitation / password-reset links in emails.
SITE_URL = os.getenv("UTILITATI_SITE_URL", "https://utilitati.nistorlazar.md")
