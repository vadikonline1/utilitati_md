"""Background invoice sync + dashboard statistics.

The sync loop runs periodically (once a day by default, configurable in /admin).
It refreshes every enabled utility account and persists invoices. Invoices whose
normalized status is already PAID are never overwritten (see
utilities.upsert_invoice_from_provider).
"""

from __future__ import annotations

import asyncio
import calendar
import logging
from datetime import datetime, timedelta

from ..config import SITE_URL
from ..db import _conn
from . import maintenance, notify, push as push_svc, utilities
from .settings import get_setting, get_sync_interval_hours, set_setting

_LOGGER = logging.getLogger(__name__)


def _enabled_accounts() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM accounts WHERE status = 'enabled'"
        ).fetchall()
    return [dict(r) for r in rows]


async def sync_all() -> dict:
    """Refresh all enabled accounts once. Returns a short summary.

    When a provider surfaces a genuinely new invoice (not seen before), the
    user is notified with the admin-editable 'invoices' message template.
    """
    accounts = _enabled_accounts()
    updated = 0
    errors = 0
    notified = 0
    for account in accounts:
        try:
            if utilities.account_is_paid(account["id"]):
                # Nothing due — skip the provider call for already-paid accounts.
                continue
            data = await utilities.fetch_account_data(account)
            created, _saved = utilities.persist_invoices(account["id"], data)
            if created:
                await notify.notify_new_invoices(
                    account["user_id"], account, data, created, SITE_URL
                )
                await notify.send_push_new_invoices(account["user_id"], created)
                notified += 1
            if data.is_connected:
                updated += 1
            else:
                errors += 1
        except Exception:  # noqa: BLE001 - keep the loop alive
            _LOGGER.exception("Sync failed for account %s", account["id"])
            errors += 1
    if notified:
        _LOGGER.info("New-invoice notifications sent to %s account(s)", notified)
    return {"checked": len(accounts), "updated": updated, "errors": errors, "notified": notified}


async def sync_loop() -> None:
    """Continuously re-schedule syncs every N hours."""
    while True:
        try:
            result = await sync_all()
            _LOGGER.info("Background sync: %s", result)
            _stamp("sync")
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Background sync failed")
        try:
            # Data-retention / inactivity cleanup runs on the same schedule.
            maintenance.run_maintenance()
            _stamp("maintenance")
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Maintenance run failed")
        try:
            # Monthly unpaid-invoices summary goes out on the 1st of the month.
            await notify_monthly_unpaid()
            _stamp("monthly")
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Monthly unpaid notification failed")
        await asyncio.sleep(get_sync_interval_hours() * 3600)


def _unpaid_rows() -> list[dict]:
    """All enabled unpaid invoices (with home/provider info), for monthly reports."""
    with _conn() as conn:
        rows = conn.execute(
            """SELECT inv.invoice_number, inv.amount_mdl,
                      a.user_id, a.provider, a.label AS account_label,
                      h.name AS home_name, h.address AS home_address
               FROM invoices inv
               JOIN accounts a ON a.id = inv.account_id
               LEFT JOIN homes h ON h.id = a.home_id
               JOIN users u ON u.id = a.user_id
               WHERE inv.status = 'enabled'
                 AND inv.amount_mdl > 0
                 AND inv.pay_status IN ('UNPAID','OVERDUE','PARTIALLY_PAID')
                 AND a.status = 'enabled'
                 AND u.is_active = 1
                 AND u.deactivated = 0
               ORDER BY a.user_id, h.name, inv.issue_date"""
        ).fetchall()
    return [dict(r) for r in rows]


async def notify_monthly_unpaid() -> int:
    """Send each user (with unpaid invoices) a month-end summary, once per period.

    Runs on the LAST day of the month. The email/Telegram message is the
    admin-editable 'unpaid' template and contains every open invoice; a push
    notification is also sent with a short summary.
    """
    now = datetime.now()
    if now.day != calendar.monthrange(now.year, now.month)[1]:
        return 0
    period_key = f"{now.year}-{now.month:02d}"
    if get_setting("monthly_unpaid_sent") == period_key:
        return 0

    by_user: dict[int, list[dict]] = {}
    for row in _unpaid_rows():
        by_user.setdefault(row["user_id"], []).append(row)

    for user_id, invoice_rows in by_user.items():
        total = sum(float(r.get("amount_mdl", 0) or 0) for r in invoice_rows)
        try:
            await notify.deliver_user_notification(
                user_id,
                "unpaid",
                count=len(invoice_rows),
                total=f"{total:.2f}",
                date=period_key,
                invoices="\n".join(notify.unpaid_lines(invoice_rows)),
                site=SITE_URL,
            )
        except Exception:  # noqa: BLE001 - don't drop the other users
            _LOGGER.exception("Monthly unpaid notification failed for user %s", user_id)
        try:
            # Short push reminder with the default text.
            await push_svc.send_push(
                user_id,
                "Facturi neachitate 🔔",
                f"Verificați facturile, aveți facturi neachitate ({len(invoice_rows)}).",
                type_="unpaid",
            )
        except Exception:  # noqa: BLE001 - don't drop the other users
            _LOGGER.exception("Monthly unpaid push failed for user %s", user_id)

    set_setting("monthly_unpaid_sent", period_key)
    _LOGGER.info("Monthly unpaid summary sent to %s user(s) (%s)", len(by_user), period_key)
    return len(by_user)


def list_user_enabled_accounts(user_id: int) -> list[dict]:
    """All enabled accounts belonging to the given user."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM accounts WHERE user_id = ? AND status = 'enabled'",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# Background invoice job queue
# --------------------------------------------------------------------------- #
def enqueue_invoice_job(user_id: int, *, account_id: int | None = None) -> int:
    """Queue a background refresh for the user's account(s).

    Inserting a row lets any worker (and any number of uvicorn workers) process
    it once, keeping oplata.md traffic serialized even when many users trigger a
    refresh at the same time. Returns the job id, or 0 when nothing to enqueue.
    """
    if account_id is not None:
        with _conn() as conn:
            exists = conn.execute(
                "SELECT id FROM accounts WHERE id = ? AND user_id = ? AND status = 'enabled'",
                (account_id, user_id),
            ).fetchone()
        if not exists:
            return 0
    elif not list_user_enabled_accounts(user_id):
        return 0
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO invoice_jobs (user_id, account_id, status) VALUES (?, ?, 'pending')",
            (user_id, account_id),
        )
        return int(cur.lastrowid)


def _claim_next_job() -> dict | None:
    """Atomically claim the oldest pending job (single-writer-safe)."""
    with _conn() as conn:
        row = conn.execute(
            """SELECT id, user_id, account_id FROM invoice_jobs
               WHERE status = 'pending' ORDER BY id LIMIT 1"""
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE invoice_jobs SET status = 'running', started_at = datetime('now')"
            " WHERE id = ? AND status = 'pending'",
            (row["id"],),
        )
        if conn.total_changes == 0:
            return None
    return dict(row)


def _finish_job(job_id: int, ok: bool, result: str = "") -> None:
    # A cancelled job must never be overwritten back to done/failed.
    with _conn() as conn:
        conn.execute(
            "UPDATE invoice_jobs SET status = ?, finished_at = datetime('now'), result = ? "
            "WHERE id = ? AND status != 'cancelled'",
            ("done" if ok else "failed", (result or "")[:500], job_id),
        )


_LAST_RUN_KEYS = {
    "sync": "jobs_last_sync",
    "maintenance": "jobs_last_maintenance",
    "monthly": "jobs_last_monthly",
    "worker": "jobs_last_worker",
}


def _stamp(key: str) -> None:
    try:
        set_setting(_LAST_RUN_KEYS[key], datetime.now().isoformat(timespec="seconds"))
    except Exception:  # noqa: BLE001 - tracking must never break the loops
        _LOGGER.exception("Could not stamp %s run time", key)


def system_jobs_status() -> list[dict]:
    """Read-only overview of the background/scheduled tasks (for /admin).

    ``schedule`` is a human-readable recurrence and ``last_run`` the most
    recent successful completion (tracked via settings keys).
    """
    hours = get_sync_interval_hours()
    return [
        {
            "key": "sync",
            "name": "Sincronizare facturi (sync_loop)",
            "schedule": f"la fiecare {hours} ore" if hours != 24 else "zilnic",
            "last_run": get_setting(_LAST_RUN_KEYS["sync"], ""),
        },
        {
            "key": "maintenance",
            "name": "Curățenie / retenție date (maintenance)",
            "schedule": "după fiecare sincronizare",
            "last_run": get_setting(_LAST_RUN_KEYS["maintenance"], ""),
        },
        {
            "key": "monthly",
            "name": "Sumar lunar facturi neachitate",
            "schedule": "ultima zi a lunii",
            "last_run": get_setting(_LAST_RUN_KEYS["monthly"], ""),
        },
        {
            "key": "worker",
            "name": "Worker joburi facturi (invoice_job_worker)",
            "schedule": "continuu (verificare la ~5s)",
            "last_run": get_setting(_LAST_RUN_KEYS["worker"], ""),
        },
    ]


def list_invoice_jobs(limit: int = 300) -> list[dict]:
    """All invoice background jobs (admin view), newest first."""
    with _conn() as conn:
        rows = conn.execute(
            """SELECT j.id, j.user_id, j.account_id, j.status, j.attempts,
                      j.created_at, j.started_at, j.finished_at, j.result,
                      u.username, a.label AS account_label
               FROM invoice_jobs j
               LEFT JOIN users u ON u.id = j.user_id
               LEFT JOIN accounts a ON a.id = j.account_id
               ORDER BY j.id DESC LIMIT ?""",
            (int(limit),),
        ).fetchall()
    return [dict(r) for r in rows]


def restart_invoice_job(job_id: int) -> bool:
    """Re-queue a job (done/failed/cancelled -> pending) so the worker retries it."""
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE invoice_jobs SET status = 'pending', attempts = attempts + 1, "
            "started_at = NULL, finished_at = NULL, result = NULL "
            "WHERE id = ? AND status != 'pending'",
            (job_id,),
        )
        return cur.rowcount > 0


def cancel_invoice_job(job_id: int) -> bool:
    """Cancel a pending/running job (it will not be claimed/overwritten)."""
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE invoice_jobs SET status = 'cancelled' "
            "WHERE id = ? AND status IN ('pending', 'running')",
            (job_id,),
        )
        return cur.rowcount > 0


def delete_invoice_job(job_id: int) -> bool:
    """Permanently remove a job row."""
    with _conn() as conn:
        cur = conn.execute("DELETE FROM invoice_jobs WHERE id = ?", (job_id,))
        return cur.rowcount > 0


def cleanup_old_jobs(keep_days: int = 7) -> int:
    """Delete finished/cancelled job rows older than keep_days. Returns count."""
    with _conn() as conn:
        cur = conn.execute(
            f"DELETE FROM invoice_jobs WHERE status IN ('done','failed','cancelled') "
            f"AND finished_at IS NOT NULL "
            f"AND finished_at < datetime('now', '-{int(keep_days)} days')"
        )
        if cur.rowcount > 0:
            _LOGGER.info("Cleaned %s old invoice job(s) (>%s days)", cur.rowcount, keep_days)
        return cur.rowcount or 0


def _cleanup_old_jobs(keep_days: int = 7) -> None:
    keep_days = max(1, int(keep_days))
    with _conn() as conn:
        conn.execute(
            f"DELETE FROM invoice_jobs WHERE status IN ('done','failed') "
            f"AND finished_at < datetime('now', '-{keep_days} days')"
        )


def job_info(job_id: int | None, user_id: int | None) -> dict | None:
    """Return a job's terminal status, or None if not found / not owned."""
    if job_id is None:
        return None
    with _conn() as conn:
        row = conn.execute(
            "SELECT user_id, status FROM invoice_jobs WHERE id = ?", (job_id,)
        ).fetchone()
    if row is None:
        return None
    if user_id is not None and row["user_id"] != user_id:
        return None
    status = row["status"]
    return {
        "finished": status in ("done", "failed"),
        "failed": status == "failed",
        "status": status,
    }


async def _process_job(job: dict) -> None:
    """Fetch + persist invoices for the job's account(s), then push if new."""
    user_id, account_id = job["user_id"], job["account_id"]
    accounts = (
        list_user_enabled_accounts(user_id)
        if account_id is None
        else [a for a in list_user_enabled_accounts(user_id) if a["id"] == account_id]
    )
    try:
        all_new: list[int] = []
        for account in accounts:
            if utilities.account_is_paid(account["id"]):
                # Nothing due — avoid an unnecessary provider call.
                continue
            data = await utilities.fetch_account_data(account)
            created, _saved = utilities.persist_invoices(account["id"], data)
            if created:
                all_new.extend(created)
                await _notify_user_new_invoices(user_id, account, created)
        if all_new:
            await notify.send_push_new_invoices(user_id, all_new)
        _finish_job(job["id"], True, f"accounts={len(accounts)}")
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Invoice job %s failed for user %s", job["id"], user_id)
        _finish_job(job["id"], False, "error")


async def _notify_user_new_invoices(
    user_id: int, account: dict, created_ids: list[int]
) -> None:
    """Fire the web (email/Telegram) template for newly discovered invoices."""
    try:
        await notify.notify_new_invoices(user_id, account, None, created_ids, SITE_URL)
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Web new-invoice notification failed for user %s", user_id)


async def invoice_job_worker() -> None:
    """Continuously process queued invoice refreshes, one at a time."""
    throttle = 2.0
    while True:
        job = _claim_next_job()
        if job is None:
            _cleanup_old_jobs()
            await asyncio.sleep(5)
            continue
        try:
            await _process_job(job)
            _stamp("worker")
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Invoice job worker crashed on job %s", job["id"])
        if throttle > 0:
            await asyncio.sleep(throttle)


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
