"""SQLite persistence layer: users, homes, accounts (utilities), invoices, history."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    notification_emails TEXT NOT NULL DEFAULT '',
    telegram_chat_ids TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS homes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    address TEXT NOT NULL DEFAULT '',
    floor TEXT DEFAULT '',
    metro_area TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'enabled',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    home_id INTEGER,
    provider TEXT NOT NULL,
    label TEXT NOT NULL,
    contract_number TEXT NOT NULL,
    place_of_consumption TEXT,
    username TEXT,
    password TEXT,
    icon TEXT,
    status TEXT NOT NULL DEFAULT 'enabled',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (home_id) REFERENCES homes (id)
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    invoice_number TEXT DEFAULT '',
    external_invoice_id TEXT,
    amount_mdl REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'MDL',
    period TEXT,
    issue_date TEXT,
    due_date TEXT,
    is_paid INTEGER NOT NULL DEFAULT 0,
    pay_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    status TEXT NOT NULL DEFAULT 'enabled',
    pdf_url TEXT,
    checked_at TEXT,
    raw_response TEXT,
    extra_details TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS invoice_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    pay_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    amount_mdl REAL NOT NULL DEFAULT 0,
    checked_at TEXT NOT NULL DEFAULT (datetime('now')),
    raw_response TEXT,
    FOREIGN KEY (invoice_id) REFERENCES invoices (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_invoices_account ON invoices (account_id);
CREATE INDEX IF NOT EXISTS idx_history_invoice ON invoice_history (invoice_id, checked_at);
"""


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with _conn() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns/tables introduced in later versions to existing databases."""
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    if "invoices" in tables:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(invoices)")}
        for col, ddl in {
            "external_invoice_id": "ALTER TABLE invoices ADD COLUMN external_invoice_id TEXT",
            "currency": "ALTER TABLE invoices ADD COLUMN currency TEXT NOT NULL DEFAULT 'MDL'",
            "period": "ALTER TABLE invoices ADD COLUMN period TEXT",
            "pay_status": "ALTER TABLE invoices ADD COLUMN pay_status TEXT NOT NULL DEFAULT 'UNKNOWN'",
            "checked_at": "ALTER TABLE invoices ADD COLUMN checked_at TEXT",
            "raw_response": "ALTER TABLE invoices ADD COLUMN raw_response TEXT",
            "extra_details": "ALTER TABLE invoices ADD COLUMN extra_details TEXT",
        }.items():
            if col not in cols:
                conn.execute(ddl)

    # Users: notification preferences (email list + telegram chat ids).
    if "users" in tables:
        ucols = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
        for col, ddl in {
            "notification_emails": "ALTER TABLE users ADD COLUMN notification_emails TEXT NOT NULL DEFAULT ''",
            "telegram_chat_ids": "ALTER TABLE users ADD COLUMN telegram_chat_ids TEXT NOT NULL DEFAULT ''",
        }.items():
            if col not in ucols:
                conn.execute(ddl)

    # Moldovagaz is Energocom: migrate legacy accounts/contracts to energocom.
    if "accounts" in tables:
        conn.execute(
            "UPDATE accounts SET provider = 'energocom' WHERE provider = 'moldovagaz'"
        )
