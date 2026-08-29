"""Service layer: homes, accounts (utilities), invoices, history and provider access."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from typing import Any

from pyutilitati_md import (
    AccountData,
    INVOICE_STATUS_OVERDUE,
    INVOICE_STATUS_PAID,
    INVOICE_STATUS_UNPAID,
    INVOICE_STATUS_UNKNOWN,
    get_provider_instance,
)
from pyutilitati_md.exceptions import (
    UtilitatiMDApiError,
    UtilitatiMDAuthError,
    UtilitatiMDConnectionError,
)

from ..db import _conn

try:
    import aiohttp

    _AIOHTTP_ERRORS = (aiohttp.ClientError,)
except ImportError:  # pragma: no cover
    _AIOHTTP_ERRORS = ()

_NETWORK_ERRORS = (
    UtilitatiMDConnectionError,
    TimeoutError,
    asyncio.TimeoutError,
    OSError,
) + _AIOHTTP_ERRORS


# --------------------------------------------------------------------------- #
# Homes
# --------------------------------------------------------------------------- #
def get_username(user_id: int) -> str | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT username FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return row["username"] if row else None


def get_notification_prefs(user_id: int) -> dict[str, str]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT notification_emails, telegram_chat_ids FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        return {"emails": "", "telegram": ""}
    return {"emails": row["notification_emails"] or "", "telegram": row["telegram_chat_ids"] or ""}


def set_notification_prefs(user_id: int, emails: str, telegram: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET notification_emails = ?, telegram_chat_ids = ? WHERE id = ?",
            (emails.strip(), telegram.strip(), user_id),
        )


def list_homes(user_id: int) -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT h.*,
                      (SELECT COUNT(*) FROM accounts a
                        WHERE a.home_id = h.id AND a.status = 'enabled')
                          AS utilities_count,
                      (SELECT COUNT(*) FROM invoices inv
                        JOIN accounts a ON a.id = inv.account_id
                        WHERE a.home_id = h.id AND inv.is_paid = 0
                          AND inv.status = 'enabled')
                          AS unpaid_invoices
               FROM homes h WHERE h.user_id = ? ORDER BY h.created_at DESC""",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_home(user_id: int, home_id: int) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM homes WHERE id = ? AND user_id = ?", (home_id, user_id)
        ).fetchone()
    return dict(row) if row else None


def create_home(user_id: int, data: dict[str, Any]) -> int:
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO homes (user_id, name, address, floor, metro_area, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                data.get("name", "Locuință"),
                data.get("address", ""),
                data.get("floor", ""),
                data.get("metro_area", ""),
                data.get("status", "enabled"),
            ),
        )
        return cur.lastrowid


def update_home(user_id: int, home_id: int, data: dict[str, Any]) -> bool:
    with _conn() as conn:
        cur = conn.execute(
            """UPDATE homes SET name = ?, address = ?, floor = ?, metro_area = ?,
               status = ? WHERE id = ? AND user_id = ?""",
            (
                data.get("name", ""),
                data.get("address", ""),
                data.get("floor", ""),
                data.get("metro_area", ""),
                data.get("status", "enabled"),
                home_id,
                user_id,
            ),
        )
        return cur.rowcount > 0


def set_home_status(user_id: int, home_id: int, status: str) -> bool:
    status = "enabled" if status == "enabled" else "disabled"
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE homes SET status = ? WHERE id = ? AND user_id = ?",
            (status, home_id, user_id),
        )
        return cur.rowcount > 0


def delete_home(user_id: int, home_id: int) -> bool:
    """Delete a home and everything attached (utilities + their invoices).
    Only allowed when the home is disabled."""
    home = get_home(user_id, home_id)
    if home is None or home.get("status") != "disabled":
        return False
    with _conn() as conn:
        conn.execute(
            "DELETE FROM accounts WHERE home_id = ? AND user_id = ?", (home_id, user_id)
        )
        cur = conn.execute(
            "DELETE FROM homes WHERE id = ? AND user_id = ?", (home_id, user_id)
        )
        return cur.rowcount > 0


# --------------------------------------------------------------------------- #
# Accounts (utilities)
# --------------------------------------------------------------------------- #
def list_accounts(user_id: int, home_id: int | None = None) -> list[dict[str, Any]]:
    with _conn() as conn:
        if home_id is not None:
            rows = conn.execute(
                "SELECT * FROM accounts WHERE user_id = ? AND home_id = ? ORDER BY label",
                (user_id, home_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM accounts WHERE user_id = ? ORDER BY label", (user_id,)
            ).fetchall()
    return [dict(r) for r in rows]


def get_account_row(user_id: int, account_id: int) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM accounts WHERE id = ? AND user_id = ?",
            (account_id, user_id),
        ).fetchone()
    return dict(row) if row else None


def upsert_account(
    user_id: int, data: dict[str, Any], account_id: int | None = None
) -> int:
    home_id = data.get("home_id")
    status = data.get("status", "enabled")
    with _conn() as conn:
        if account_id:
            conn.execute(
                """UPDATE accounts SET provider = ?, label = ?, contract_number = ?,
                   place_of_consumption = ?, username = ?, password = ?, icon = ?,
                   home_id = ?, status = ?
                   WHERE id = ? AND user_id = ?""",
                (
                    data["provider"], data.get("label", ""), data["contract_number"],
                    data.get("place_of_consumption"), data.get("username"),
                    data.get("password"), data.get("icon"), home_id, status,
                    account_id, user_id,
                ),
            )
            return account_id
        cur = conn.execute(
            """INSERT INTO accounts
               (user_id, home_id, provider, label, contract_number,
                place_of_consumption, username, password, icon, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id, home_id, data["provider"], data.get("label", ""),
                data["contract_number"], data.get("place_of_consumption"),
                data.get("username"), data.get("password"), data.get("icon"), status,
            ),
        )
        return cur.lastrowid


def set_account_status(user_id: int, account_id: int, status: str) -> bool:
    status = "enabled" if status == "enabled" else "disabled"
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE accounts SET status = ? WHERE id = ? AND user_id = ?",
            (status, account_id, user_id),
        )
        return cur.rowcount > 0


def delete_account(user_id: int, account_id: int) -> bool:
    with _conn() as conn:
        cur = conn.execute(
            "DELETE FROM accounts WHERE id = ? AND user_id = ?", (account_id, user_id)
        )
        return cur.rowcount > 0


# --------------------------------------------------------------------------- #
# Invoices (stored locally) + invoice history
# --------------------------------------------------------------------------- #
def list_invoices(
    user_id: int,
    account_id: int | None = None,
    home_id: int | None = None,
) -> list[dict[str, Any]]:
    query = """
        SELECT inv.*, a.label AS account_label, a.icon AS account_icon,
               a.home_id AS home_id, a.provider AS provider,
               h.name AS home_name
        FROM invoices inv
        JOIN accounts a ON a.id = inv.account_id
        LEFT JOIN homes h ON h.id = a.home_id
        WHERE a.user_id = ?
    """
    conds: list[Any] = [user_id]
    if account_id is not None:
        query += " AND inv.account_id = ?"
        conds.append(account_id)
    if home_id is not None:
        query += " AND a.home_id = ?"
        conds.append(home_id)
    query += " ORDER BY inv.issue_date DESC, inv.id DESC"
    with _conn() as conn:
        rows = conn.execute(query, conds).fetchall()
    return [_decode_invoice(dict(r)) for r in rows]


def _decode_invoice(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("extra_details"):
        try:
            row["extra_details"] = json.loads(row["extra_details"])
        except (ValueError, TypeError):
            row["extra_details"] = None
    return row


def create_invoice(
    user_id: int, account_id: int, data: dict[str, Any]
) -> int | None:
    """Manually add an invoice to an account owned by the user. Returns the new id."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT id FROM accounts WHERE id = ? AND user_id = ?",
            (account_id, user_id),
        ).fetchone()
        if row is None:
            return None
        try:
            amount = float(data.get("amount_mdl", 0) or 0)
        except (TypeError, ValueError):
            amount = 0
        is_paid = int(bool(data.get("is_paid", False)))
        pay_status = INVOICE_STATUS_PAID if is_paid else INVOICE_STATUS_UNPAID
        cur = conn.execute(
            """INSERT INTO invoices
               (account_id, invoice_number, amount_mdl, issue_date, due_date,
                is_paid, pay_status, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                account_id,
                data.get("invoice_number", ""),
                amount,
                data.get("issue_date") or None,
                data.get("due_date") or None,
                is_paid,
                pay_status,
                data.get("status", "enabled"),
            ),
        )
        return cur.lastrowid


def get_invoice(user_id: int, invoice_id: int) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute(
            """SELECT inv.* FROM invoices inv
               JOIN accounts a ON a.id = inv.account_id
               WHERE inv.id = ? AND a.user_id = ?""",
            (invoice_id, user_id),
        ).fetchone()
    return _decode_invoice(dict(row)) if row else None


def normalize_status(
    amount_mdl: float, is_paid: bool, due_date: date | str | None
) -> str:
    """Map an invoice to one of the normalized statuses."""
    if is_paid:
        return INVOICE_STATUS_PAID
    if amount_mdl > 0:
        if due_date:
            due = due_date if isinstance(due_date, date) else _parse_date(due_date)
            if due is not None and due < date.today():
                return INVOICE_STATUS_OVERDUE
        return INVOICE_STATUS_UNPAID
    return INVOICE_STATUS_PAID if amount_mdl == 0 else INVOICE_STATUS_UNKNOWN


def upsert_invoice_from_provider(account_id: int, invoice: Any) -> int | None:
    """Save an Invoice returned by a provider into the local store (deduped).
    Appends a row to invoice_history on each provider check."""
    if invoice is None:
        return None
    invoice_number = getattr(invoice, "invoice_number", "") or ""
    amount = float(getattr(invoice, "amount_mdl", 0) or 0)
    issue_date = _to_str(getattr(invoice, "issue_date", None))
    due_date = _to_str(getattr(invoice, "due_date", None))
    is_paid = bool(getattr(invoice, "is_paid", False))
    pdf_url = getattr(invoice, "pdf_url", None)
    currency = getattr(invoice, "currency", "MDL") or "MDL"
    period = getattr(invoice, "period", None)
    external_invoice_id = getattr(invoice, "external_invoice_id", None)
    raw_response = getattr(invoice, "raw_response", None)
    checked_at = _to_str(getattr(invoice, "checked_at", None)) or _now_str()
    pay_status = normalize_status(amount, is_paid, getattr(invoice, "due_date", None))
    extra_details = getattr(invoice, "extra_details", None) or {}
    extra_json = json.dumps(extra_details, ensure_ascii=False, default=str)

    with _conn() as conn:
        existing = conn.execute(
            "SELECT id, pay_status FROM invoices WHERE account_id = ? AND invoice_number = ?",
            (account_id, invoice_number),
        ).fetchone()
        if existing:
            inv_id = existing["id"]
            # Once an invoice is marked PAID it is final: do not overwrite it
            # with a later (possibly inconsistent) provider amount/status.
            if existing["pay_status"] == INVOICE_STATUS_PAID:
                return inv_id
            conn.execute(
                """UPDATE invoices SET amount_mdl = ?, currency = ?, period = ?,
                   issue_date = ?, due_date = ?, is_paid = ?, pay_status = ?,
                   external_invoice_id = ?, pdf_url = ?, checked_at = ?,
                   raw_response = ?, extra_details = ?, updated_at = datetime('now')
                   WHERE id = ?""",
                (amount, currency, period, issue_date, due_date, int(is_paid),
                 pay_status, external_invoice_id, pdf_url, checked_at,
                 raw_response, extra_json, inv_id),
            )
        else:
            cur = conn.execute(
                """INSERT INTO invoices
                   (account_id, invoice_number, external_invoice_id, amount_mdl,
                    currency, period, issue_date, due_date, is_paid, pay_status,
                    pdf_url, checked_at, raw_response, extra_details)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (account_id, invoice_number, external_invoice_id, amount,
                 currency, period, issue_date, due_date, int(is_paid), pay_status,
                 pdf_url, checked_at, raw_response, extra_json),
            )
            inv_id = cur.lastrowid

        conn.execute(
            """INSERT INTO invoice_history
               (invoice_id, pay_status, amount_mdl, checked_at, raw_response)
               VALUES (?, ?, ?, ?, ?)""",
            (inv_id, pay_status, amount, checked_at, raw_response),
        )
        return inv_id


def persist_invoices(account_id: int, data: Any) -> list[int]:
    """Persist all invoices returned by a provider (falling back to last_invoice).

    Dedupes against the local store and appends invoice_history rows, so a
    single provider check may now update several historic invoices at once.
    """
    invoices = getattr(data, "invoices", None)
    if not invoices:
        last = getattr(data, "last_invoice", None)
        invoices = [last] if last is not None else []
    saved: list[int] = []
    for inv in invoices:
        inv_id = upsert_invoice_from_provider(account_id, inv)
        if inv_id is not None:
            saved.append(inv_id)
    return saved


def list_invoice_history(user_id: int, invoice_id: int) -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT h.* FROM invoice_history h
               JOIN invoices inv ON inv.id = h.invoice_id
               JOIN accounts a ON a.id = inv.account_id
               WHERE h.invoice_id = ? AND a.user_id = ?
               ORDER BY h.checked_at DESC""",
            (invoice_id, user_id),
        ).fetchall()
    return [dict(r) for r in rows]


def update_invoice(user_id: int, invoice_id: int, data: dict[str, Any]) -> bool:
    invoice = get_invoice(user_id, invoice_id)
    if invoice is None:
        return False
    with _conn() as conn:
        is_paid = int(bool(data.get("is_paid", invoice["is_paid"])))
        cur = conn.execute(
            """UPDATE invoices SET amount_mdl = ?, currency = ?, period = ?,
               issue_date = ?, due_date = ?, is_paid = ?, pay_status = ?,
               pdf_url = ?, status = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (
                float(data.get("amount_mdl", invoice["amount_mdl"] or 0)),
                data.get("currency") or invoice["currency"],
                data.get("period") or invoice["period"],
                data.get("issue_date") or invoice["issue_date"],
                data.get("due_date") or invoice["due_date"],
                is_paid,
                INVOICE_STATUS_PAID if is_paid else invoice["pay_status"],
                data.get("pdf_url") or invoice["pdf_url"],
                data.get("status", "enabled"),
                invoice_id,
            ),
        )
        return cur.rowcount > 0


def set_invoice_status(user_id: int, invoice_id: int, status: str) -> bool:
    status = "enabled" if status == "enabled" else "disabled"
    with _conn() as conn:
        cur = conn.execute(
            """UPDATE invoices SET status = ?, updated_at = datetime('now')
               WHERE id = ? AND account_id IN
               (SELECT id FROM accounts WHERE user_id = ?)""",
            (status, invoice_id, user_id),
        )
        return cur.rowcount > 0


def delete_invoice(user_id: int, invoice_id: int) -> bool:
    with _conn() as conn:
        cur = conn.execute(
            """DELETE FROM invoices WHERE id = ? AND account_id IN
               (SELECT id FROM accounts WHERE user_id = ?)""",
            (invoice_id, user_id),
        )
        return cur.rowcount > 0


# --------------------------------------------------------------------------- #
# Provider access
# --------------------------------------------------------------------------- #
def _build_client(account: dict[str, Any]):
    return get_provider_instance(
        provider_id=account["provider"],
        contract_number=account["contract_number"],
        username=account.get("username"),
        password=account.get("password"),
        place_of_consumption=account.get("place_of_consumption"),
    )


async def fetch_account_data(account: dict[str, Any]) -> AccountData:
    """Fetch live data; persist the last invoice + history locally."""
    client = _build_client(account)

    def _fail(message: str) -> AccountData:
        return AccountData(
            contract_number=account["contract_number"],
            provider_id=account["provider"],
            provider_name=account.get("label", account["provider"]),
            is_connected=False,
            error_message=message,
            last_updated=datetime.now(),
        )

    try:
        data = await client.async_fetch_data()
        # Preserve normalized pay_status on the last invoice.
        if data.last_invoice is not None:
            data.last_invoice.checked_at = datetime.now()
        return data
    except UtilitatiMDAuthError as err:
        return _fail(
            f"Date de autentificare invalide sau contul {account['contract_number']} "
            f"nu a fost găsit: {err}."
        )
    except UtilitatiMDConnectionError as err:
        return _fail(f"Furnizorul este indisponibil sau nu a răspuns la timp: {err}.")
    except (TimeoutError, asyncio.TimeoutError, OSError) as err:
        return _fail(f"Furnizorul nu a răspuns la timp (timeout): {err}.")
    except UtilitatiMDApiError as err:
        return _fail(f"Platforma furnizorului a returnat un răspuns neașteptat: {err}.")
    except _AIOHTTP_ERRORS as err:
        return _fail(f"Eroare de conexiune la platforma furnizorului: {err}.")


async def submit_meter_reading(account: dict[str, Any], reading_value: float) -> bool:
    client = _build_client(account)
    return await client.async_submit_meter_reading(reading_value)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _now_str() -> str:
    return datetime.now().isoformat()


def _parse_date(value: str | date) -> date | None:
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(value)[:10], fmt).date()
        except ValueError:
            continue
    return None
