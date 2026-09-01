"""Persistence layer: SQLite (default) or MySQL (via env).

The rest of the code base talks to the database through a single helper,
`_conn()`, returning a connection whose `.execute()` returns a cursor exposing
`.lastrowid` and `.rowcount`, and whose rows support `row["column"]` mapping
access. This module provides that API for both SQLite and MySQL.

Backend selection (matching the pattern used for SMTP / Telegram settings):

* If any `UTILITATI_MYSQL_*` variables are set (or `UTILITATI_DB_ENGINE=mysql`),
  the app connects to MySQL and `/admin` can manage the connection settings
  through the database (see `app/services/settings.py`).
* Otherwise it falls back to SQLite using `UTILITATI_DB` (or `utilitati.db`).

Users: homes, accounts (utilities), invoices, history.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterator

try:
    import pymysql

    _HAS_MYSQL = True
except Exception:  # pragma: no cover - import error means no PyMySQL
    pymysql = None
    _HAS_MYSQL = False

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

CREATE INDEX IF NOT EXISTS idx_invoices_account ON invoices (account_id);
CREATE INDEX IF NOT EXISTS idx_history_invoice ON invoice_history (invoice_id, checked_at);
"""

# --------------------------------------------------------------------------- #
# Backend selection
# --------------------------------------------------------------------------- #
MYSQL_ENV = {
    "host": "UTILITATI_MYSQL_HOST",
    "port": "UTILITATI_MYSQL_PORT",
    "user": "UTILITATI_MYSQL_USER",
    "password": "UTILITATI_MYSQL_PASSWORD",
    "db": "UTILITATI_MYSQL_DB",
    "charset": "UTILITATI_MYSQL_CHARSET",
}


def _mysql_env() -> dict | None:
    """Return a MySQL connection config (env vars win, then a JSON sidecar
    written by the admin UI), or None if MySQL is not configured."""
    env_cfg = _mysql_from_env()
    if env_cfg is not None:
        return env_cfg
    file_cfg = load_mysql_config_file()
    if file_cfg is not None:
        return file_cfg
    return None


def _mysql_from_env() -> dict | None:
    engine = os.getenv("UTILITATI_DB_ENGINE", "").strip().lower()
    if engine != "mysql" and not any(os.getenv(v) for v in MYSQL_ENV.values()):
        return None
    return {
        "host": os.getenv("UTILITATI_MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("UTILITATI_MYSQL_PORT", "3306")),
        "user": os.getenv("UTILITATI_MYSQL_USER", "root"),
        "password": os.getenv("UTILITATI_MYSQL_PASSWORD", ""),
        "db": os.getenv("UTILITATI_MYSQL_DB", "utilitati"),
        "charset": os.getenv("UTILITATI_MYSQL_CHARSET", "utf8mb4"),
    }


def _mysql_config_file() -> Path:
    # Sidecar lives next to the application config (sibling of the package).
    return Path(DB_PATH).resolve().parent / "mysql_config.json"


def load_mysql_config_file() -> dict | None:
    """Read the JSON sidecar written by the admin UI, if present."""
    try:
        path = _mysql_config_file()
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not data:
            return None
        return {
            "host": str(data.get("host", "127.0.0.1")),
            "port": int(data.get("port", 3306)),
            "user": str(data.get("user", "root")),
            "password": str(data.get("password", "")),
            "db": str(data.get("db", "utilitati")),
            "charset": str(data.get("charset", "utf8mb4")),
        }
    except Exception:
        return None


def save_mysql_config_file(data: dict) -> None:
    """Persist MySQL connection settings for the admin UI. Env vars still win."""
    path = _mysql_config_file()
    payload = {
        "host": str(data.get("host", "127.0.0.1")),
        "port": int(data.get("port", 3306)),
        "user": str(data.get("user", "root")),
        "password": str(data.get("password", "")),
        "db": str(data.get("db", "utilitati")),
        "charset": str(data.get("charset", "utf8mb4")),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def using_mysql() -> bool:
    """True when the app is running against MySQL (not SQLite)."""
    return bool(_mysql_env()) and _HAS_MYSQL


# --------------------------------------------------------------------------- #
# SQLite
# --------------------------------------------------------------------------- #
@contextmanager
def _sqlite_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# MySQL
# --------------------------------------------------------------------------- #
_PLACEHOLDER_RE = re.compile(r"\?")


def _translate_sql(sql: str) -> str:
    """Adapt SQLite SQL to MySQL where the two dialects differ.

    * `?` param placeholders -> `%s` (PyMySQL paramstyle)
    * `datetime('now')` / `date('now')` -> `NOW()` / `CURDATE()`
    * `INSERT ... ON CONFLICT(key) DO UPDATE SET a=excluded.a` -> upsert
    * integer primary key mirrored manually (DDL differs, handled separately)
    """
    sql = _PLACEHOLDER_RE.sub("%s", sql)

    if "datetime('now')" in sql:
        sql = sql.replace("datetime('now')", "NOW()")
    if "date('now')" in sql:
        sql = sql.replace("date('now')", "CURDATE()")

    # sqlite `datetime(<col>)` (already handled 'now' above) -> plain column
    sql = re.sub(r"\bdatetime\(([A-Za-z_][A-Za-z0-9_]*)\)", r"\1", sql)

    # sqlite: INSERT ... ON CONFLICT(key) DO UPDATE SET col = excluded.col
    m = re.search(
        r"INSERT\s+INTO\s+(\w+)\s+\(([^)]*)\)\s*VALUES\s*\(([^)]*)\)"
        r"\s*ON\s+CONFLICT\s*\(\s*(\w+)\s*\)\s*DO\s+UPDATE\s+SET\s+(.+)$",
        sql,
        re.IGNORECASE,
    )
    if m:
        table, cols, placeholders, conflict_key, assignments = m.groups()
        assign_parts = assignments.split(",")
        new_list = []
        for part in assign_parts:
            part = part.strip()
            mset = re.match(r"^(\w+)\s*=\s*excluded\.(\w+)$", part, re.IGNORECASE)
            if mset:
                new_list.append(f"{mset.group(1)} = VALUES({mset.group(2)})")
            elif re.match(r"^(\w+)\s*=\s*%s$", part, re.IGNORECASE):
                new_list.append(part)
            else:
                new_list.append(part)
        sql = (
            f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) "
            f"ON DUPLICATE KEY UPDATE {', '.join(new_list)}"
        )

    # `key` is a reserved word in MySQL and is only ever used in this codebase
    # as the settings table's primary-key column. Backtick it in the specific
    # contexts the app uses (INSERT column list, SELECT list, WHERE predicate).
    sql = sql.replace("INSERT INTO settings (key,", "INSERT INTO settings (`key`,")
    sql = sql.replace("SELECT key,", "SELECT `key`,")
    sql = sql.replace("WHERE key =", "WHERE `key` =")
    sql = sql.replace("WHERE key LIKE", "WHERE `key` LIKE")
    sql = sql.replace("ORDER BY key", "ORDER BY `key`")

    return sql


class _MyCursor:
    """Thin wrapper exposing lastrowid / rowcount like sqlite's cursor."""

    def __init__(self, cur: Any) -> None:
        self._cur = cur

    @property
    def lastrowid(self) -> int:
        try:
            return int(self._cur.lastrowid)
        except (TypeError, ValueError):
            return 0

    @property
    def rowcount(self) -> int:
        return int(self._cur.rowcount)

    def fetchone(self):
        row = self._cur.fetchone()
        return dict(row) if row else None

    def fetchall(self):
        return [dict(r) for r in self._cur.fetchall()]


class _MyConnection:
    """Emulate the sqlite3 connection API used throughout the app on MySQL."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def execute(self, sql: str, params: Any = ()) -> _MyCursor:
        if params is None:
            params = ()
        translated = _translate_sql(sql)
        try:
            cur = self._conn.cursor()
            cur.execute(translated, tuple(params))
            return _MyCursor(cur)
        except Exception as err:
            # Persist partially-applied sqlite-style updates are not an issue:
            # re-raise with a helpful message including the translated statement.
            raise type(err)(f"{err} (sql: {translated})") from err

    def executescript(self, script: str) -> None:
        # executescript implicitly commits; split on ';' and run each statement.
        for stmt in script.split(";"):
            stmt = stmt.strip()
            if not stmt:
                continue
            self.execute(stmt)

    def commit(self) -> None:
        try:
            self._conn.commit()
        except Exception as err:  # pragma: no cover
            raise type(err)(f"commit failed: {err}") from err

    def rollback(self) -> None:
        try:
            self._conn.rollback()
        except Exception:  # pragma: no cover
            pass

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:  # pragma: no cover
            pass


@contextmanager
def _mysql_conn() -> Iterator[_MyConnection]:
    cfg = _mysql_env()
    if cfg is None or not _HAS_MYSQL:
        raise RuntimeError(
            "MySQL is enabled but PyMySQL is not installed. "
            "Add `pymysql` to requirements.txt."
        )
    kw = dict(cfg)
    kw.pop("db", None)
    conn = pymysql.connect(
        host=cfg["host"],
        port=cfg.get("port", 3306),
        user=cfg["user"],
        password=cfg.get("password", ""),
        database=cfg["db"],
        charset=cfg.get("charset", "utf8mb4"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        **kw,
    )
    wrapped = _MyConnection(conn)
    try:
        yield wrapped
        wrapped.commit()
    finally:
        wrapped.close()


# --------------------------------------------------------------------------- #
# Public connection entry point
# --------------------------------------------------------------------------- #
@contextmanager
def _conn() -> Iterator[Any]:
    if using_mysql():
        with _mysql_conn() as conn:
            yield conn
    else:
        with _sqlite_conn() as conn:
            yield conn


def _sqlite_has_column(conn, table: str, column: str) -> bool:
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    return column in cols


def _mysql_has_column(conn, table: str, column: str) -> bool:
    rows = conn.execute(
        f"SHOW COLUMNS FROM `{table}` LIKE %s", (column,)
    ).fetchall()
    return bool(rows)


def _has_column(conn, table: str, column: str) -> bool:
    if using_mysql():
        return _mysql_has_column(conn, table, column)
    return _sqlite_has_column(conn, table, column)


def _has_table(conn, table: str) -> bool:
    if using_mysql():
        rows = conn.execute(
            "SELECT COUNT(*) AS c FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = %s", (table,)
        ).fetchall()
        return bool(rows) and int(rows[0]["c"]) > 0
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,)
    ).fetchall()
    return bool(rows)


def _mysql_idempotent_ddl(conn, table: str, column: str, ddl: str) -> None:
    """Run `[ADD COLUMN]/CREATE` only if not already present (MySQL helper)."""
    if column and _has_column(conn, table, column):
        return
    conn.execute(ddl)


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


def _migrate_mysql(conn) -> None:
    # Query information_schema for the table set.
    rows = conn.execute(
        "SELECT table_name AS t FROM information_schema.tables "
        "WHERE table_schema = DATABASE()"
    ).fetchall()
    tables = {r["t"] for r in rows}

    if "invoices" in tables:
        for col, ddl in {
            "external_invoice_id": "ALTER TABLE invoices ADD COLUMN external_invoice_id TEXT NULL",
            "currency": "ALTER TABLE invoices ADD COLUMN currency VARCHAR(8) NOT NULL DEFAULT 'MDL'",
            "period": "ALTER TABLE invoices ADD COLUMN period VARCHAR(64) NULL",
            "pay_status": "ALTER TABLE invoices ADD COLUMN pay_status VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN'",
            "checked_at": "ALTER TABLE invoices ADD COLUMN checked_at VARCHAR(64) NULL",
            "raw_response": "ALTER TABLE invoices ADD COLUMN raw_response LONGTEXT NULL",
            "extra_details": "ALTER TABLE invoices ADD COLUMN extra_details LONGTEXT NULL",
        }.items():
            if not _has_column(conn, "invoices", col):
                conn.execute(ddl)

    if "contact_messages" in tables and not _has_column(conn, "contact_messages", "subject"):
        conn.execute("ALTER TABLE contact_messages ADD COLUMN subject VARCHAR(255) NOT NULL DEFAULT ''")

    if "users" in tables:
        for col, ddl in {
            "notification_emails": "ALTER TABLE users ADD COLUMN notification_emails TEXT NOT NULL",
            "telegram_chat_ids": "ALTER TABLE users ADD COLUMN telegram_chat_ids TEXT NOT NULL",
            "full_name": "ALTER TABLE users ADD COLUMN full_name VARCHAR(255) NOT NULL DEFAULT ''",
            "email": "ALTER TABLE users ADD COLUMN email VARCHAR(255) NOT NULL DEFAULT ''",
            "is_active": "ALTER TABLE users ADD COLUMN is_active TINYINT NOT NULL DEFAULT 0",
            "confirm_token": "ALTER TABLE users ADD COLUMN confirm_token VARCHAR(255) NULL",
            "reset_token": "ALTER TABLE users ADD COLUMN reset_token VARCHAR(255) NULL",
            "reset_token_exp": "ALTER TABLE users ADD COLUMN reset_token_exp VARCHAR(64) NULL",
            "lang": "ALTER TABLE users ADD COLUMN lang VARCHAR(8) NOT NULL DEFAULT ''",
            "last_login": "ALTER TABLE users ADD COLUMN last_login VARCHAR(64) NULL",
            "last_inactivity_email": "ALTER TABLE users ADD COLUMN last_inactivity_email VARCHAR(64) NULL",
            "deactivated": "ALTER TABLE users ADD COLUMN deactivated TINYINT NOT NULL DEFAULT 0",
            "delete_after": "ALTER TABLE users ADD COLUMN delete_after VARCHAR(64) NULL",
        }.items():
            if not _has_column(conn, "users", col):
                conn.execute(ddl)
        conn.execute(
            "UPDATE users SET last_login = COALESCE(last_login, created_at) "
            "WHERE is_active = 1"
        )

    if "accounts" in tables:
        if not _has_column(conn, "accounts", "full_name"):
            conn.execute("ALTER TABLE accounts ADD COLUMN full_name VARCHAR(255) NULL")
        conn.execute(
            "UPDATE accounts SET provider = 'energocom' WHERE provider = 'moldovagaz'"
        )

    for index, table, col in (
        ("idx_invoices_account", "invoices", "account_id"),
        ("idx_history_invoice", "invoice_history", "invoice_id"),
    ):
        try:
            conn.execute(f"CREATE INDEX {index} ON {table} ({col})")
        except Exception:
            pass


def init_db() -> None:
    if using_mysql():
        if not _HAS_MYSQL:
            raise RuntimeError("PyMySQL is required to use MySQL. Install it.")
        with _mysql_conn() as conn:
            conn.executescript(_mysql_schema())
            _migrate_mysql(conn)
    else:
        Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        with _sqlite_conn() as conn:
            conn.executescript(SCHEMA)
            _migrate_sqlite(conn)
    _seed_common()


def _mysql_schema() -> str:
    """MySQL equivalent of `SCHEMA`, built from the same table definitions.

    Uses `CREATE TABLE IF NOT EXISTS` with MySQL types. Columns added by
    `_migrate_mysql` already default correctly (VARCHAR/TINYINT), so here we
    only create the base tables the app depends on.
    """
    return """
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(191) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        full_name VARCHAR(255) NOT NULL DEFAULT '',
        email VARCHAR(255) NOT NULL DEFAULT '',
        is_active TINYINT NOT NULL DEFAULT 0,
        confirm_token VARCHAR(255) NULL,
        reset_token VARCHAR(255) NULL,
        reset_token_exp VARCHAR(64) NULL,
        notification_emails TEXT NOT NULL,
        telegram_chat_ids TEXT NOT NULL,
        deactivated TINYINT NOT NULL DEFAULT 0,
        delete_after VARCHAR(64) NULL,
        lang VARCHAR(8) NOT NULL DEFAULT '',
        last_login VARCHAR(64) NULL,
        last_inactivity_email VARCHAR(64) NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    CREATE TABLE IF NOT EXISTS contact_messages (
        id INT AUTO_INCREMENT PRIMARY KEY,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        name VARCHAR(255) NOT NULL DEFAULT '',
        email VARCHAR(255) NOT NULL DEFAULT '',
        subject VARCHAR(255) NOT NULL DEFAULT '',
        message TEXT NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    CREATE TABLE IF NOT EXISTS faq_items (
        id INT AUTO_INCREMENT PRIMARY KEY,
        sort_order INT NOT NULL DEFAULT 0,
        question_ro TEXT NOT NULL,
        question_ru TEXT NOT NULL,
        question_en TEXT NOT NULL,
        answer_ro TEXT NOT NULL,
        answer_ru TEXT NOT NULL,
        answer_en TEXT NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    CREATE TABLE IF NOT EXISTS settings (
        `key` VARCHAR(191) PRIMARY KEY,
        `value` LONGTEXT NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    CREATE TABLE IF NOT EXISTS pages (
        id INT AUTO_INCREMENT PRIMARY KEY,
        slug VARCHAR(191) NOT NULL UNIQUE,
        title_ro TEXT NOT NULL,
        title_ru TEXT NOT NULL,
        title_en TEXT NOT NULL,
        content_ro LONGTEXT NOT NULL,
        content_ru LONGTEXT NOT NULL,
        content_en LONGTEXT NOT NULL,
        meta_title TEXT NOT NULL,
        meta_description TEXT NOT NULL,
        is_builtin TINYINT NOT NULL DEFAULT 0,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    CREATE TABLE IF NOT EXISTS homes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        name VARCHAR(255) NOT NULL,
        address VARCHAR(255) NOT NULL DEFAULT '',
        floor VARCHAR(64) DEFAULT '',
        metro_area VARCHAR(128) DEFAULT '',
        status VARCHAR(16) NOT NULL DEFAULT 'enabled',
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    CREATE TABLE IF NOT EXISTS accounts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        home_id INT NULL,
        provider VARCHAR(64) NOT NULL,
        label VARCHAR(255) NOT NULL,
        contract_number VARCHAR(255) NOT NULL,
        place_of_consumption VARCHAR(255) NULL,
        username TEXT NULL,
        password TEXT NULL,
        full_name VARCHAR(255) NULL,
        icon VARCHAR(16) NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'enabled',
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (home_id) REFERENCES homes(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    CREATE TABLE IF NOT EXISTS invoices (
        id INT AUTO_INCREMENT PRIMARY KEY,
        account_id INT NOT NULL,
        invoice_number VARCHAR(255) DEFAULT '',
        external_invoice_id VARCHAR(255) NULL,
        amount_mdl DECIMAL(14,2) NOT NULL DEFAULT 0,
        currency VARCHAR(8) NOT NULL DEFAULT 'MDL',
        period VARCHAR(64) NULL,
        issue_date VARCHAR(32) NULL,
        due_date VARCHAR(32) NULL,
        is_paid TINYINT NOT NULL DEFAULT 0,
        pay_status VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN',
        status VARCHAR(16) NOT NULL DEFAULT 'enabled',
        pdf_url VARCHAR(512) NULL,
        checked_at VARCHAR(64) NULL,
        raw_response LONGTEXT NULL,
        extra_details LONGTEXT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    CREATE TABLE IF NOT EXISTS invoice_history (
        id INT AUTO_INCREMENT PRIMARY KEY,
        invoice_id INT NOT NULL,
        pay_status VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN',
        amount_mdl DECIMAL(14,2) NOT NULL DEFAULT 0,
        checked_at VARCHAR(64) NOT NULL,
        raw_response LONGTEXT NULL,
        FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """


def _seed_common() -> None:
    """Seed FAQ + pages (shared across backends). Kept after schema/migration so
    the tables definitely exist."""
    with _conn() as conn:
        from .services.faq import seed_default_faq
        seed_default_faq(conn)
        from .services.pages import seed_default_pages
        seed_default_pages(conn)
