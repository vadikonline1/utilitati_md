"""Background invoice sync + dashboard statistics.

The sync loop runs periodically (once a day by default, configurable in /admin).
It refreshes every enabled utility account and persists invoices. Invoices whose
normalized status is already PAID are never overwritten (see
utilities.upsert_invoice_from_provider).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from ..db import _conn
from . import utilities
from .settings import get_sync_interval_hours

_LOGGER = logging.getLogger(__name__)


def _enabled_accounts() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM accounts WHERE status = 'enabled'"
        ).fetchall()
    return [dict(r) for r in rows]


async def sync_all() -> dict:
    """Refresh all enabled accounts once. Returns a short summary."""
    accounts = _enabled_accounts()
    updated = 0
    errors = 0
    for account in accounts:
        try:
            data = await utilities.fetch_account_data(account)
            utilities.persist_invoices(account["id"], data)
            if data.is_connected:
                updated += 1
            else:
                errors += 1
        except Exception:  # noqa: BLE001 - keep the loop alive
            _LOGGER.exception("Sync failed for account %s", account["id"])
            errors += 1
    return {"checked": len(accounts), "updated": updated, "errors": errors}


async def sync_loop() -> None:
    """Continuously re-schedule syncs every N hours."""
    while True:
        try:
            result = await sync_all()
            _LOGGER.info("Background sync: %s", result)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Background sync failed")
        await asyncio.sleep(get_sync_interval_hours() * 3600)


def list_user_enabled_accounts(user_id: int) -> list[dict]:
    """All enabled accounts belonging to the given user."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM accounts WHERE user_id = ? AND status = 'enabled'",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


async def generate_invoices_for_user(
    user_id: int, *, account_id: int | None = None, throttle: float = 2.0
) -> dict:
    """Fetch invoices for a user's account(s), sequentially and rate-limited.

    Throttling (a short await between accounts) plus single-account calls keeps
    the provider traffic low and avoids flooding the Oplata endpoints. Invoices
    already marked PAID are never overwritten.
    """
    if account_id is not None:
        accounts = [
            a for a in list_user_enabled_accounts(user_id) if a["id"] == account_id
        ]
    else:
        accounts = list_user_enabled_accounts(user_id)

    updated = 0
    errors = 0
    checked = []
    for account in accounts:
        try:
            data = await utilities.fetch_account_data(account)
            utilities.persist_invoices(account["id"], data)
            checked.append(account["id"])
            if data.is_connected:
                updated += 1
            else:
                errors += 1
        except Exception:  # noqa: BLE001 - continue with the next account
            _LOGGER.exception("Invoice generation failed for account %s", account["id"])
            errors += 1
        if throttle > 0 and account is not accounts[-1]:
            await asyncio.sleep(throttle)

    return {
        "checked_accounts": len(accounts),
        "updated_accounts": updated,
        "errors": errors,
        "invoice_count": 0,
    }


# --------------------------------------------------------------------------- #
# Dashboard statistics
# --------------------------------------------------------------------------- #
def dashboard_stats(user_id: int) -> dict:
    """Aggregate per-user invoice stats for the dashboard charts."""
    with _conn() as conn:
        homes_count = conn.execute(
            "SELECT COUNT(*) AS c FROM homes WHERE user_id = ? AND status = 'enabled'",
            (user_id,),
        ).fetchone()["c"]
        accounts_count = conn.execute(
            "SELECT COUNT(*) AS c FROM accounts "
            "WHERE user_id = ? AND status = 'enabled'",
            (user_id,),
        ).fetchone()["c"]
        unpaid_total = conn.execute(
            "SELECT COALESCE(SUM(inv.amount_mdl), 0) AS s "
            "FROM invoices inv JOIN accounts a ON a.id = inv.account_id "
            "WHERE a.user_id = ? AND inv.status = 'enabled' AND inv.pay_status IN "
            "('UNPAID','OVERDUE','PARTIALLY_PAID')",
            (user_id,),
        ).fetchone()["s"]
        open_count = conn.execute(
            "SELECT COUNT(*) AS c FROM invoices inv JOIN accounts a ON a.id = inv.account_id "
            "WHERE a.user_id = ? AND inv.status = 'enabled' AND inv.pay_status IN "
            "('UNPAID','OVERDUE','PARTIALLY_PAID') AND inv.amount_mdl > 0",
            (user_id,),
        ).fetchone()["c"]
        paid_count = conn.execute(
            "SELECT COUNT(*) AS c FROM invoices inv JOIN accounts a ON a.id = inv.account_id "
            "WHERE a.user_id = ? AND inv.pay_status = 'PAID'",
            (user_id,),
        ).fetchone()["c"]
        due_count = conn.execute(
            "SELECT COUNT(*) AS c FROM invoices inv JOIN accounts a ON a.id = inv.account_id "
            "WHERE a.user_id = ? AND inv.status = 'enabled' AND inv.pay_status = 'OVERDUE'",
            (user_id,),
        ).fetchone()["c"]

        by_provider = {}
        for row in conn.execute(
            "SELECT a.provider AS p, COALESCE(SUM(inv.amount_mdl), 0) AS s "
            "FROM invoices inv JOIN accounts a ON a.id = inv.account_id "
            "WHERE a.user_id = ? AND inv.status = 'enabled' AND inv.pay_status IN "
            "('UNPAID','OVERDUE','PARTIALLY_PAID') GROUP BY a.provider",
            (user_id,),
        ).fetchall():
            by_provider[row["p"]] = round(row["s"], 2)

        by_status = {}
        for row in conn.execute(
            "SELECT inv.pay_status AS st, COUNT(*) AS c "
            "FROM invoices inv JOIN accounts a ON a.id = inv.account_id "
            "WHERE a.user_id = ? AND inv.status = 'enabled' GROUP BY inv.pay_status",
            (user_id,),
        ).fetchall():
            by_status[row["st"]] = row["c"]

    return {
        "homes": homes_count,
        "accounts": accounts_count,
        "unpaid_total": round(unpaid_total, 2),
        "open_count": open_count,
        "paid_count": paid_count,
        "overdue_count": due_count,
        "by_provider": by_provider,
        "by_status": by_status,
        "generated_at": datetime.now(),
    }
