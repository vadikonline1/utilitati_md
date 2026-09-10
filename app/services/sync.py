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


_MANUAL_RUN_KEYS = ("sync", "maintenance", "monthly")

_wake_event: asyncio.Event | None = None


def _ensure_wake_event() -> asyncio.Event:
    """Return the shared wake-up event, creating it on the running loop once.

    Created lazily inside ``sync_loop`` (never at import time) so the event is
    bound to the actual uvicorn/asyncio event loop regardless of Python version.
    """
    global _wake_event
    if _wake_event is None:
        _wake_event = asyncio.Event()
    return _wake_event


def request_manual_run(job_key: str) -> bool:
    """Queue a one-off run of a system job (admin "Run now" button)."""
    if job_key not in _MANUAL_RUN_KEYS:
        return False
    set_setting(f"job_manual_{job_key}", datetime.now().isoformat(timespec="seconds"))
    ev = _wake_event
    if ev is not None:
        ev.set()
    return True


def _consume_manual_runs() -> set[str]:
    """Return and clear any queued manual run flags (works across restarts)."""
    pending: set[str] = set()
    for key in _MANUAL_RUN_KEYS:
        if get_setting(f"job_manual_{key}", ""):
            set_setting(f"job_manual_{key}", "")
            pending.add(key)
    return pending


def _midnight(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _last_run_dt(key: str) -> datetime | None:
    raw = get_setting(_LAST_RUN_KEYS[key], "")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _current_sync_slot(now: datetime) -> datetime:
    """The most recent sync slot <= now (aligned to 00:00)."""
    hours = max(1, get_sync_interval_hours())
    base = _midnight(now)
    elapsed = (now - base).total_seconds() / 3600.0
    k = int(elapsed // hours)
    return base + timedelta(hours=k * hours)


def _next_sync_slot(now: datetime) -> datetime:
    """Next sync run time, strictly after `now`, aligned to 00:00."""
    hours = max(1, get_sync_interval_hours())
    base = _midnight(now)
    elapsed = (now - base).total_seconds() / 3600.0
    k = int(elapsed // hours) + 1
    return base + timedelta(hours=k * hours)


def _current_slot_for(key: str, now: datetime) -> datetime | None:
    """The most recent scheduled slot <= now (None if no slot has arrived)."""
    if key == "sync":
        return _current_sync_slot(now)
    if key == "maintenance":
        return _midnight(now)
    # monthly: the last day of the current month at 00:00.
    last_day = calendar.monthrange(now.year, now.month)[1]
    slot = datetime(now.year, now.month, last_day)
    return slot if slot <= now else None


def _next_run_for(key: str, now: datetime) -> datetime:
    if key == "sync":
        return _next_sync_slot(now)
    if key == "maintenance":
        return _midnight(now) + timedelta(days=1)
    # monthly: last day of current month (or next month if already past).
    last_day = calendar.monthrange(now.year, now.month)[1]
    nxt = datetime(now.year, now.month, last_day)
    return nxt if nxt > now else _last_day_of_next_month(now)


def _last_day_of_next_month(now: datetime) -> datetime:
    if now.month == 12:
        year, month = now.year + 1, 1
    else:
        year, month = now.year, now.month + 1
    last_day = calendar.monthrange(year, month)[1]
    return datetime(year, month, last_day)


def _is_due(key: str, now: datetime) -> bool:
    """True when the current slot arrived and this run hasn't happened yet."""
    slot = _current_slot_for(key, now)
    if slot is None:
        return False
    last = _last_run_dt(key)
    return last is None or last < slot


async def _run_system_job(key: str, force: bool = False) -> None:
    """Execute a single scheduled job (sync / maintenance / monthly)."""
    if key == "sync":
        result = await sync_all()
        _LOGGER.info("Background sync: %s", result)
        _stamp("sync")
    elif key == "maintenance":
        maintenance.run_maintenance()
        _stamp("maintenance")
    elif key == "monthly":
        await notify_monthly_unpaid(force=force)
        _stamp("monthly")


async def sync_loop() -> None:
    """Scheduler aligning every system job to its 00:00 slot.

    Each job runs when its current aligned slot arrives (and only once per
    slot), supports a one-off manual run (see request_manual_run) and catches
    up after a restart: a job whose slot passed while the app was down is
    executed on the next loop iteration.
    """
    while True:
        wake_event = _ensure_wake_event()
        now = datetime.now()
        manual = _consume_manual_runs()
        for key in _MANUAL_RUN_KEYS:
            if key in manual or _is_due(key, now):
                try:
                    await _run_system_job(key, force=(key in manual))
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("System job %s failed", key)
        # Sleep until the next aligned slot (wake up early on manual runs).
        soonest = min(_next_run_for(k, datetime.now()) for k in _MANUAL_RUN_KEYS)
        delay = max(1.0, min(3600.0, (soonest - datetime.now()).total_seconds()))
        try:
            await asyncio.wait_for(wake_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass
        finally:
            wake_event.clear()


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


async def notify_monthly_unpaid(*, force: bool = False) -> int:
    """Send each user (with unpaid invoices) a month-end summary, once per period.

    Runs on the LAST day of the month. The email/Telegram message is the
    admin-editable 'unpaid' template and contains every open invoice; a push
    notification is also sent with a short summary. ``force=True`` (manual run)
    bypasses the last-day check but keeps the once-per-period dedupe.
    """
    now = datetime.now()
    if not force and now.day != calendar.monthrange(now.year, now.month)[1]:
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

    ``schedule`` is a human-readable recurrence, ``last_run`` the most recent
    completion (tracked via settings keys) and ``next_run`` the next aligned
    00:00 slot. ``runnable`` marks jobs that support the admin "Run now" button.
    """
    hours = get_sync_interval_hours()
    now = datetime.now()

    def fmt(dt: datetime | None) -> str:
        if dt is None:
            return ""
        return dt.strftime("%d.%m.%Y %H:%M")

    def fmt_last(key: str) -> str:
        raw = get_setting(_LAST_RUN_KEYS[key], "")
        if not raw:
            return ""
        try:
            return fmt(datetime.fromisoformat(raw))
        except ValueError:
            return raw

    def job(key: str, name: str, schedule: str) -> dict:
        return {
            "key": key,
            "name": name,
            "schedule": schedule,
            "last_run": fmt_last(key),
            "next_run": "",
            "runnable": key in _MANUAL_RUN_KEYS,
        }

    sync_job = job(
        "sync",
        "Sincronizare facturi (sync_loop)",
        f"zilnic la 00:00" if hours >= 24 else f"la fiecare {hours} ore (prima la 00:00)",
    )
    sync_job["next_run"] = fmt(_next_run_for("sync", now))

    maintenance_job = job(
        "maintenance",
        "Curățenie / retenție date (maintenance)",
        "zilnic la 00:00",
    )
    maintenance_job["next_run"] = fmt(_next_run_for("maintenance", now))

    monthly_job = job(
        "monthly",
        "Sumar lunar facturi neachitate",
        "ultima zi a lunii la 00:00",
    )
    monthly_job["next_run"] = fmt(_next_run_for("monthly", now))

    worker_job = job(
        "worker",
        "Worker joburi facturi (invoice_job_worker)",
        "continuu (verificare la ~5s)",
    )
    worker_job["next_run"] = "continuu"

    return [sync_job, maintenance_job, monthly_job, worker_job]


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


def dashboard_tables(user_id: int, limit: int = 50) -> dict:
    """Current-month invoices for the dashboard table (unpaid first)."""
    month = datetime.now().strftime("%Y-%m")
    with _conn() as conn:
        rows = conn.execute(
            "SELECT inv.invoice_number, inv.amount_mdl, inv.pay_status, "
            "inv.checked_at, inv.issue_date, "
            "a.label AS account_label, a.provider AS provider, "
            "h.name AS home_name "
            "FROM invoices inv JOIN accounts a ON a.id = inv.account_id "
            "LEFT JOIN homes h ON h.id = a.home_id "
            "WHERE a.user_id = ? AND inv.status = 'enabled' AND a.status = 'enabled' "
            "AND inv.pay_status IN ('PAID','UNPAID','OVERDUE','PARTIALLY_PAID') "
            "AND strftime('%Y-%m', COALESCE(inv.issue_date, inv.checked_at)) = ? "
            "ORDER BY CASE WHEN inv.pay_status IN ('UNPAID','OVERDUE','PARTIALLY_PAID') "
            "THEN 0 ELSE 1 END, COALESCE(inv.checked_at, inv.issue_date) DESC LIMIT ?",
            (user_id, month, int(limit)),
        ).fetchall()
    return {"rows": [dict(r) for r in rows]}
