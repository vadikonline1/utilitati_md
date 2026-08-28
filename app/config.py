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
