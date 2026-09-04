"""Persistence layer for Utilități Moldova — SQLite only.

The entire code base talks to the database through a single helper, `_conn()`,
which opens a fresh SQLite connection per operation (context manager). Every
connection configures WAL journaling + a busy timeout so the server can handle
many concurrent readers and (serialized) writers without `database is locked`
errors.

Schema covers: users, contact_messages, faq_items, settings, pages, homes,
accounts (utilities), invoices, invoice_history.
"""

from __future__ import annotations

from contextlib import contextmanager
import sqlite3
from pathlib import Path
from typing import Any, Iterator

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 0,
    confirm_token TEXT,
    reset_token TEXT,
    reset_token_exp TEXT,
    notification_emails TEXT NOT NULL DEFAULT '',
    telegram_chat_ids TEXT NOT NULL DEFAULT '',
    deactivated INTEGER NOT NULL DEFAULT 0,
    delete_after TEXT,
    lang TEXT NOT NULL DEFAULT '',
    last_login TEXT,
    last_inactivity_email TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS contact_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    name TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS faq_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    question_ro TEXT NOT NULL DEFAULT '',
    question_ru TEXT NOT NULL DEFAULT '',
    question_en TEXT NOT NULL DEFAULT '',
    answer_ro TEXT NOT NULL DEFAULT '',
    answer_ru TEXT NOT NULL DEFAULT '',
    answer_en TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    title_ro TEXT NOT NULL DEFAULT '',
    title_ru TEXT NOT NULL DEFAULT '',
    title_en TEXT NOT NULL DEFAULT '',
    content_ro TEXT NOT NULL DEFAULT '',
    content_ru TEXT NOT NULL DEFAULT '',
    content_en TEXT NOT NULL DEFAULT '',
    meta_title TEXT NOT NULL DEFAULT '',
    meta_description TEXT NOT NULL DEFAULT '',
    is_builtin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
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
    full_name TEXT,
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

CREATE TABLE IF NOT EXISTS device_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    platform TEXT NOT NULL DEFAULT 'android',
    token TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'expo',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, token),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS invoice_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    account_id INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    finished_at TEXT,
    result TEXT,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_invoices_account ON invoices (account_id);
CREATE INDEX IF NOT EXISTS idx_history_invoice ON invoice_history (invoice_id, checked_at);
CREATE INDEX IF NOT EXISTS idx_device_tokens_user ON device_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_invoice_jobs_pending ON invoice_jobs (status, id);
"""


@contextmanager
def _sqlite_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Concurrent-read/write friendliness: WAL journaling + busy timeout let the
    # server handle many readers and (serialized) writers without locking up.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA synchronous = NORMAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


@contextmanager
def _conn() -> Iterator[Any]:
    """Open a fresh SQLite connection (the single DB entry point)."""
    with _sqlite_conn() as conn:
        yield conn


def _sqlite_has_column(conn, table: str, column: str) -> bool:
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    return column in cols


def _migrate_sqlite(conn) -> None:
    tables = {
        r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    if "invoices" in tables:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(invoices)").fetchall()}
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

    if "contact_messages" in tables:
        ccols = {r["name"] for r in conn.execute("PRAGMA table_info(contact_messages)").fetchall()}
        if "subject" not in ccols:
            conn.execute("ALTER TABLE contact_messages ADD COLUMN subject TEXT NOT NULL DEFAULT ''")

    if "users" in tables:
        ucols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        for col, ddl in {
            "notification_emails": "ALTER TABLE users ADD COLUMN notification_emails TEXT NOT NULL DEFAULT ''",
            "telegram_chat_ids": "ALTER TABLE users ADD COLUMN telegram_chat_ids TEXT NOT NULL DEFAULT ''",
            "full_name": "ALTER TABLE users ADD COLUMN full_name TEXT NOT NULL DEFAULT ''",
            "email": "ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''",
            "is_active": "ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 0",
            "confirm_token": "ALTER TABLE users ADD COLUMN confirm_token TEXT",
            "reset_token": "ALTER TABLE users ADD COLUMN reset_token TEXT",
            "reset_token_exp": "ALTER TABLE users ADD COLUMN reset_token_exp TEXT",
            "lang": "ALTER TABLE users ADD COLUMN lang TEXT NOT NULL DEFAULT ''",
            "last_login": "ALTER TABLE users ADD COLUMN last_login TEXT",
            "last_inactivity_email": "ALTER TABLE users ADD COLUMN last_inactivity_email TEXT",
            "deactivated": "ALTER TABLE users ADD COLUMN deactivated INTEGER NOT NULL DEFAULT 0",
            "delete_after": "ALTER TABLE users ADD COLUMN delete_after TEXT",
        }.items():
            if col not in ucols:
                conn.execute(ddl)
        conn.execute(
            "UPDATE users SET last_login = COALESCE(last_login, created_at) "
            "WHERE is_active = 1"
        )

    if "accounts" in tables:
        acols = {r["name"] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()}
        if "full_name" not in acols:
            conn.execute("ALTER TABLE accounts ADD COLUMN full_name TEXT")
        conn.execute(
            "UPDATE accounts SET provider = 'energocom' WHERE provider = 'moldovagaz'"
        )

    if "device_tokens" in tables:
        dcols = {r["name"] for r in conn.execute("PRAGMA table_info(device_tokens)").fetchall()}
        if "provider" not in dcols:
            conn.execute(
                "ALTER TABLE device_tokens ADD COLUMN provider TEXT NOT NULL DEFAULT 'expo'"
            )

    if "faq_items" not in tables:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS faq_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                question_ro TEXT NOT NULL DEFAULT '',
                question_ru TEXT NOT NULL DEFAULT '',
                question_en TEXT NOT NULL DEFAULT '',
                answer_ro TEXT NOT NULL DEFAULT '',
                answer_ru TEXT NOT NULL DEFAULT '',
                answer_en TEXT NOT NULL DEFAULT ''
            )
            """
        )


def init_db() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with _sqlite_conn() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.executescript(SCHEMA)
        _migrate_sqlite(conn)
    _seed_common()


def _seed_common() -> None:
    """Seed FAQ + pages (kept so the tables exist)."""
    with _conn() as conn:
        from .services.faq import seed_default_faq
        seed_default_faq(conn)
        from .services.pages import seed_default_pages
        seed_default_pages(conn)