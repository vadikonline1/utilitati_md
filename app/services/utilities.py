"""Service layer: homes, accounts (utilities), invoices, history and provider access."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
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
from . import crypto

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
    emails = row["notification_emails"] or ""
    telegram = row["telegram_chat_ids"] or ""
    if crypto.is_encrypted(emails):
        emails = crypto.decrypt(emails) or ""
    if crypto.is_encrypted(telegram):
        telegram = crypto.decrypt(telegram) or ""
    return {"emails": emails, "telegram": telegram}


def set_notification_prefs(user_id: int, emails: str, telegram: str) -> None:
    enc_emails = crypto.encrypt(emails.strip()) or ""
    enc_telegram = crypto.encrypt(telegram.strip()) or ""
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET notification_emails = ?, telegram_chat_ids = ? WHERE id = ?",
            (enc_emails, enc_telegram, user_id),
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
def _with_creds(account: dict[str, Any]) -> dict[str, Any]:
    """Return the account dict with username/password decrypted (safe copy)."""
    out = dict(account)
    for key in ("username", "password"):
        raw = out.get(key)
        if crypto.is_encrypted(raw):
            out[key] = crypto.decrypt(raw)
    return out


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
    return [_with_creds(dict(r)) for r in rows]


def get_account_row(user_id: int, account_id: int) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM accounts WHERE id = ? AND user_id = ?",
            (account_id, user_id),
        ).fetchone()
    return _with_creds(dict(row)) if row else None


def upsert_account(
    user_id: int, data: dict[str, Any], account_id: int | None = None
) -> int:
    home_id = data.get("home_id")
    status = data.get("status", "enabled")
    full_name = data.get("full_name")
    # Providers that need a full name get the user's profile full_name as the
    # default (e.g. Stroy Master Domofon, VIP Interfon, LEGION SECURITY GROUP).
    if not full_name:
        with _conn() as conn:
            row = conn.execute(
                "SELECT full_name FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        if row:
            full_name = row["full_name"] or None
    # Credentials are encrypted at rest; every read path decrypts them on use.
    enc_username = crypto.safe_encrypt(data.get("username") or None)
    enc_password = crypto.safe_encrypt(data.get("password") or None)
    with _conn() as conn:
        if account_id:
            conn.execute(
                """UPDATE accounts SET provider = ?, label = ?, contract_number = ?,
                   place_of_consumption = ?, username = ?, password = ?, icon = ?,
                   full_name = ?, home_id = ?, status = ?
                   WHERE id = ? AND user_id = ?""",
                (
                    data["provider"], data.get("label", ""), data["contract_number"],
                    data.get("place_of_consumption"), enc_username, enc_password,
                    data.get("icon"), full_name, home_id, status, account_id, user_id,
                ),
            )
            return account_id
        cur = conn.execute(
            """INSERT INTO accounts
               (user_id, home_id, provider, label, contract_number,
                place_of_consumption, username, password, icon, full_name, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id, home_id, data["provider"], data.get("label", ""),
                data["contract_number"], data.get("place_of_consumption"),
                enc_username, enc_password, data.get("icon"), full_name, status,
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
    pay_status_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Invoices for the user (optionally scoped), unpaid first.

    pay_status_filter: None (all), 'unpaid' (UNPAID/OVERDUE/PARTIALLY_PAID),
    or 'paid' (PAID only).
    """
    query = """
        SELECT inv.*, a.label AS account_label, a.icon AS account_icon,
               a.home_id AS home_id, a.provider AS provider,
               a.contract_number AS contract_number,
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
    if pay_status_filter == "unpaid":
        query += " AND inv.pay_status IN ('UNPAID','OVERDUE','PARTIALLY_PAID')"
    elif pay_status_filter == "paid":
        query += " AND inv.pay_status = 'PAID'"
    query += """ ORDER BY CASE WHEN inv.pay_status IN
                ('UNPAID','OVERDUE','PARTIALLY_PAID') THEN 0 ELSE 1 END,
                inv.issue_date DESC, inv.id DESC"""
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


def upsert_invoice_from_provider(account_id: int, invoice: Any) -> tuple[int | None, bool]:
    """Save an Invoice returned by a provider into the local store (deduped).
    Appends a row to invoice_history on each provider check.
    Returns (invoice_id | None, is_new) where is_new True only on first insert.

    Zero-amount invoices are never generated: when the provider verifies 0.00
    the invoice is considered absent/paid — an existing unpaid row is closed
    as PAID, otherwise nothing is stored.
    """
    if invoice is None:
        return None, False
    invoice_number = getattr(invoice, "invoice_number", "") or ""
    amount = float(getattr(invoice, "amount_mdl", 0) or 0)
    is_new = False
    issue_date = _to_str(getattr(invoice, "issue_date", None))
    due_date = _month_end_date(issue_date)
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
            "SELECT id, pay_status, amount_mdl FROM invoices WHERE account_id = ? AND invoice_number = ?",
            (account_id, invoice_number),
        ).fetchone()
        changed = False
        if amount == 0:
            # 0.00 means "no debt present": close an existing unpaid row as
            # PAID, but never generate a new zero-amount invoice.
            if existing and existing["pay_status"] != INVOICE_STATUS_PAID:
                inv_id = existing["id"]
                conn.execute(
                    """UPDATE invoices SET is_paid = 1, pay_status = ?,
                       checked_at = ?, updated_at = datetime('now') WHERE id = ?""",
                    (INVOICE_STATUS_PAID, checked_at, inv_id),
                )
                conn.execute(
                    """INSERT INTO invoice_history
                       (invoice_id, pay_status, amount_mdl, checked_at, raw_response)
                       VALUES (?, ?, ?, ?, ?)""",
                    (inv_id, INVOICE_STATUS_PAID, 0, checked_at, raw_response),
                )
                return inv_id, False
            return None, False
        if existing:
            inv_id = existing["id"]
            # Once an invoice is marked PAID it is final: do not overwrite it
            # with a later (possibly inconsistent) provider amount/status.
            if existing["pay_status"] == INVOICE_STATUS_PAID:
                return inv_id, False
            # Log history only on a real change (status or amount): repeated
            # identical verifications (e.g. infosapr cumulative totals) must
            # not pile up duplicate rows. The row's checked_at stays fresh.
            changed = (
                existing["pay_status"] != pay_status
                or abs(float(existing["amount_mdl"] or 0) - amount) > 0.005
            )
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
            is_new = True

        if is_new or changed:
            conn.execute(
                """INSERT INTO invoice_history
                   (invoice_id, pay_status, amount_mdl, checked_at, raw_response)
                   VALUES (?, ?, ?, ?, ?)""",
                (inv_id, pay_status, amount, checked_at, raw_response),
            )
        return inv_id, is_new


def _deactivate_superseded_infosapr(account_id: int, keep_ids: list[int]) -> None:
    """Deactivate unpaid INFOSAPR invoices that are superseded by a newer one.

    INFOSAPR returns a single cumulative amount that already includes prior
    invoices, so any older unresolved invoice of the same account is fully
    contained in the newest one. Hide invoices that are NOT in the list just
    saved (keep_ids), leaving the newest active.
    """
    placeholders = ",".join("?" for _ in keep_ids)
    with _conn() as conn:
        conn.execute(
            f"""UPDATE invoices SET status = 'disabled', updated_at = datetime('now')
                WHERE account_id = ?
                  AND is_paid = 0
                  AND pay_status != 'PAID'
                  AND status != 'disabled'
                  AND id NOT IN ({placeholders})""",
            (account_id, *keep_ids),
        )


def _mark_missing_oplata_paid(account_id: int, current_numbers: set[str]) -> int:
    """Close unpaid invoices absent from the latest oplata.md response as PAID.

    The oplata.md `/payment/check` answer is the full current debt list: an
    invoice that was due before and no longer shows up (or verifies at 0.00)
    is considered paid. Only enabled, non-PAID rows are touched, and every
    closure is recorded in invoice_history. Returns the closed count.
    """
    marked = 0
    checked_at = _now_str()
    with _conn() as conn:
        rows = conn.execute(
            """SELECT id, invoice_number, amount_mdl FROM invoices
               WHERE account_id = ? AND status != 'disabled'
                 AND pay_status != 'PAID'""",
            (account_id,),
        ).fetchall()
        for row in rows:
            if (row["invoice_number"] or "") in current_numbers:
                continue
            conn.execute(
                """UPDATE invoices SET is_paid = 1, pay_status = 'PAID',
                   checked_at = ?, updated_at = datetime('now') WHERE id = ?""",
                (checked_at, row["id"]),
            )
            conn.execute(
                """INSERT INTO invoice_history
                   (invoice_id, pay_status, amount_mdl, checked_at, raw_response)
                   VALUES (?, 'PAID', ?, ?, ?)""",
                (row["id"], row["amount_mdl"], checked_at, "oplata: absent from provider response"),
            )
            marked += 1
    return marked


def _is_oplata_provider(provider_id: str) -> bool:
    """True for generic oplata.md-backed providers (full debt list semantics)."""
    try:
        from pyutilitati_md.providers.oplata_utility import OPLATA_PROVIDERS
    except ImportError:  # pragma: no cover
        return False
    return (provider_id or "") in OPLATA_PROVIDERS


def _disable_duplicate_invoice(account_id: int, invoice_number: str) -> None:
    """Hide a duplicate-shape row (kept in DB with its history for audit)."""
    with _conn() as conn:
        row = conn.execute(
            """SELECT id, pay_status, amount_mdl FROM invoices
               WHERE account_id = ? AND invoice_number = ? AND status != 'disabled'""",
            (account_id, invoice_number),
        ).fetchone()
        if row is None:
            return
        conn.execute(
            "UPDATE invoices SET status = 'disabled', updated_at = datetime('now') WHERE id = ?",
            (row["id"],),
        )
        conn.execute(
            """INSERT INTO invoice_history
               (invoice_id, pay_status, amount_mdl, checked_at, raw_response)
               VALUES (?, ?, ?, ?, ?)""",
            (row["id"], row["pay_status"], row["amount_mdl"], _now_str(), "duplicat: aceeasi factura in alta forma"),
        )


def persist_invoices(account_id: int, data: Any) -> tuple[list[int], list[int]]:
    """Persist all invoices returned by a provider (falling back to last_invoice).

    Dedupes against the local store and appends invoice_history rows, so a
    single provider check may now update several historic invoices at once.
    For oplata.md-backed providers the answer is the full current debt list,
    so previously-unpaid invoices missing from it are closed as PAID.

    Oplata answers come in two shapes for the same debt — per-bill rows and
    one collapsed `{PROVIDER}-{contract}` row. When the collapsed row carries
    the amount of an already-open per-bill row it is the SAME bill twice:
    the per-bill row wins and the duplicate is retired.
    Returns (newly_created_ids, all_saved_ids).
    """
    invoices = getattr(data, "invoices", None)
    if not invoices:
        last = getattr(data, "last_invoice", None)
        invoices = [last] if last is not None else []
    with _conn() as conn:
        acc = conn.execute(
            "SELECT provider, contract_number FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
    provider = (acc["provider"] or "") if acc else ""
    contract = (acc["contract_number"] or "") if acc else ""
    oplata = bool(getattr(data, "is_connected", False)) and _is_oplata_provider(provider)

    # Open rows, to detect a collapsed single-form answer duplicating them.
    open_rows: list[dict] = []
    if oplata and invoices:
        with _conn() as conn:
            open_rows = [
                dict(r)
                for r in conn.execute(
                    """SELECT invoice_number, amount_mdl FROM invoices
                       WHERE account_id = ? AND status != 'disabled' AND pay_status != 'PAID'""",
                    (account_id,),
                ).fetchall()
            ]

    nonzero = [inv for inv in invoices if float(getattr(inv, "amount_mdl", 0) or 0) > 0]
    skip_numbers: set[str] = set()
    seen_extra: set[str] = set()
    disable_numbers: set[str] = set()
    if oplata and len(nonzero) == 1 and open_rows and provider and contract:
        s = nonzero[0]
        s_num = (getattr(s, "invoice_number", "") or "")
        s_amt = float(getattr(s, "amount_mdl", 0) or 0)
        if s_num == f"{provider.upper()}-{contract}":
            splits = [r for r in open_rows if (r["invoice_number"] or "") != s_num]
            if splits:
                total = round(sum(float(r["amount_mdl"] or 0) for r in splits), 2)
                matched = [r for r in splits if abs(float(r["amount_mdl"] or 0) - s_amt) < 0.005]
                if matched and abs(total - s_amt) >= 0.005:
                    for r in matched:
                        seen_extra.add(r["invoice_number"] or "")
                    skip_numbers.add(s_num)
                    disable_numbers.add(s_num)
                # else: collapsed view (single == sum of splits) or genuinely
                # new debt → normal path below.

    saved: list[int] = []
    created: list[int] = []
    current_numbers: set[str] = set(seen_extra)
    for inv in invoices:
        number = (getattr(inv, "invoice_number", "") or "")
        if not number or number in skip_numbers:
            continue
        if float(getattr(inv, "amount_mdl", 0) or 0) > 0:
            current_numbers.add(number)
        inv_id, is_new = upsert_invoice_from_provider(account_id, inv)
        if inv_id is not None:
            saved.append(inv_id)
            if is_new:
                created.append(inv_id)

    for num in disable_numbers:
        _disable_duplicate_invoice(account_id, num)

    # INFOSAPR ("summed invoice") providers emit a single cumulative total that
    # already contains any previously-invoiced amount. Keep only the newest
    # unpaid invoice: deactivate the superseded ones so old + new do not both
    # count toward the balance.
    if acc is not None and (acc["provider"] or "") == "infosapr" and saved:
        _deactivate_superseded_infosapr(account_id, saved)

    # Oplata providers: close stale unpaid rows missing from this (successful,
    # non-empty) verification as PAID — paid, not found, or verified at 0.00.
    if oplata and invoices:
        _mark_missing_oplata_paid(account_id, current_numbers)

    return created, saved


def active_unpaid_balance(account_id: int) -> float:
    """Sum unpaid amounts of the active (enabled) invoices for an account."""
    with _conn() as conn:
        row = conn.execute(
            """SELECT COALESCE(SUM(amount_mdl), 0) AS s FROM invoices
               WHERE account_id = ? AND is_paid = 0 AND status != 'disabled'""",
            (account_id,),
        ).fetchone()
    return round(float(dict(row)["s"]), 2)


def account_is_paid(account_id: int) -> bool:
    """True when the account has no active unpaid invoice (nothing due)."""
    with _conn() as conn:
        row = conn.execute(
            """SELECT 1 FROM invoices
               WHERE account_id = ? AND is_paid = 0 AND status != 'disabled'
               AND pay_status IN ('UNPAID','OVERDUE','PARTIALLY_PAID')
               LIMIT 1""",
            (account_id,),
        ).fetchone()
    return row is None


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
    """Set an invoice payment mark or visibility.

    'paid' -> is_paid=1, pay_status='PAID'; 'unpaid' -> reopened as UNPAID;
    'enabled'/'disabled' -> visibility toggle (default disabled for safety).
    """
    key = (status or "").strip().lower()
    with _conn() as conn:
        if key == "paid":
            cur = conn.execute(
                """UPDATE invoices SET is_paid = 1, pay_status = 'PAID',
                   checked_at = datetime('now'), updated_at = datetime('now')
                   WHERE id = ? AND account_id IN
                   (SELECT id FROM accounts WHERE user_id = ?)""",
                (invoice_id, user_id),
            )
        elif key == "unpaid":
            cur = conn.execute(
                """UPDATE invoices SET is_paid = 0, pay_status = 'UNPAID',
                   updated_at = datetime('now')
                   WHERE id = ? AND account_id IN
                   (SELECT id FROM accounts WHERE user_id = ?)""",
                (invoice_id, user_id),
            )
        else:
            vis = "enabled" if key == "enabled" else "disabled"
            cur = conn.execute(
                """UPDATE invoices SET status = ?, updated_at = datetime('now')
                   WHERE id = ? AND account_id IN
                   (SELECT id FROM accounts WHERE user_id = ?)""",
                (vis, invoice_id, user_id),
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
    account = _with_creds(account)
    return get_provider_instance(
        provider_id=account["provider"],
        contract_number=account["contract_number"],
        username=account.get("username"),
        password=account.get("password"),
        full_name=account.get("full_name"),
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


def _month_end_date(value: str | date | None) -> str | None:
    """Last calendar day of the month of the given date, as YYYY-MM-DD."""
    d = _parse_date(value)
    if d is None:
        return None
    if d.month == 12:
        end = date(d.year + 1, 1, 1)
    else:
        end = date(d.year, d.month + 1, 1)
    return (end - timedelta(days=1)).isoformat()
