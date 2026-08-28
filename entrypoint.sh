#!/bin/sh
# Startup entrypoint: make the database directory (bind mount or named volume)
# writable by the non-root appuser — a freshly host-created ./data dir is owned
# by root, so sqlite3 would fail with 'unable to open database file'. We fix
# ownership as root, then drop privileges and run the app as appuser.
set -e

DATA_DIR="$(dirname "${UTILITATI_DB:-/app/data/utilitati.db}")"
mkdir -p "$DATA_DIR"
chown -R appuser:appuser "$DATA_DIR"

APP_CMD="uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"

if command -v setpriv >/dev/null 2>&1; then
    exec setpriv --reuid=appuser --regid=appuser --clear-groups $APP_CMD
fi

# Fallbacks for images without setpriv: prefer su, else run as root.
if command -v su >/dev/null 2>&1; then
    exec su appuser -s /bin/sh -c "$APP_CMD"
fi

exec sh -c "$APP_CMD"
