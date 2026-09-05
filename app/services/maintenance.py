"""Automatic data-retention + inactivity cleanup jobs.

Runs alongside the background sync loop (once per scheduled run when enabled in
/admin). Jobs:

1. Inactivity: users who have not authenticated for more than `inactive_months`
   are warned by email `warn_days` before the 1-year mark, then permanently
   deleted once the limit is exceeded (unless they sign in again).
2. Old invoices: invoices older than `invoice_months` are permanently deleted.
3. Unconfirmed accounts: accounts that were never confirmed are deleted after
   `unconfirmed_hours` (default 1 hour).
4. Deactivated accounts: user-requested deletions are executed once their
   30-day grace period passes.

Jobs 3 and 4 are explicit business rules and always run, even when the general
retention toggle is off.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from ..auth import get_user, get_user_lang
from ..config import SITE_URL
from ..db import _conn
from . import email as email_svc
from .settings import (
    inactive_months,
    invoice_months,
    retention_enabled,
    unconfirmed_hours,
    warn_days,
)

_LOGGER = logging.getLogger(__name__)
_DEFAULT_LANG = "ro"


def _iso_seconds_ago(hours: float) -> str:
    return (datetime.now() - timedelta(hours=hours)).isoformat()


def _iso_days_ago(days: float) -> str:
    return (datetime.now() - timedelta(days=days)).isoformat()


def _delete_user(conn, user_id: int) -> None:
    # accounts -> invoices cascade via FK ON DELETE, so deleting the user's
    # accounts removes their invoices; homes are removed explicitly.
    conn.execute("DELETE FROM accounts WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM homes WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


def _send_inactivity_warning(user_id: int, days: int, delete_date: str) -> None:
    user = get_user(user_id)
    if not user or not user.get("email"):
        return
    lang = get_user_lang(user_id) or _DEFAULT_LANG
    try:
        delivered = email_svc.send_inactivity_warning(
            user["email"],
            user.get("full_name", "") or user.get("username", ""),
            days,
            delete_date,
            SITE_URL,
            lang=lang,
        )
    except Exception:  # noqa: BLE001 - never crash the maintenance loop
        _LOGGER.exception("Inactivity warning email failed for user %s", user_id)
        return
    # Only record that we warned when email was actually configured/delivered,
    # otherwise we will retry next run.
    if delivered:
        with _conn() as conn:
            conn.execute(
                "UPDATE users SET last_inactivity_email = datetime('now') "
                "WHERE id = ?",
                (user_id,),
            )


def _run_inactivity(conn) -> dict:
    months = inactive_months()
    # Delete users who were inactive longer than the retention period.
    cutoff = _iso_days_ago(months * 30.0)
    delete_cutoff_date = (
        datetime.now() - timedelta(days=months * 30)
    ).date().isoformat()
    deleted = 0
    warned = 0
    rows = conn.execute(
        "SELECT id, last_login, last_inactivity_email FROM users "
        "WHERE is_active = 1 AND deactivated = 0"
    ).fetchall()
    for row in rows:
        last_login = row["last_login"] or row["last_login"]
        if not last_login:
            continue
        try:
            login_dt = datetime.fromisoformat(last_login)
        except ValueError:
            continue
        age = datetime.now() - login_dt

        if age > timedelta(days=months * 30):
            _delete_user(conn, row["id"])
            deleted += 1
            continue

        # Send warnings at the configured days-before-deletion thresholds, once
        # each (tracked via last_inactivity_email).
        for days in warn_days():
            try:
                last_warn = (
                    datetime.fromisoformat(row["last_inactivity_email"])
                    if row["last_inactivity_email"]
                    else None
                )
            except ValueError:
                last_warn = None
            # Only warn if this specific threshold hasn't been hit yet.
            if last_warn is not None and last_warn >= login_dt:
                continue
            age_days = age.days
            if age_days >= (months * 30) - days:
                delete_date = (
                    login_dt + timedelta(days=months * 30)
                ).date().isoformat()
                _send_inactivity_warning(row["id"], days, delete_date)
                warned += 1
                break  # send at most one warning per run per user
    return {"deleted_users": deleted, "warnings_sent": warned}


def _run_invoices(conn) -> dict:
    months = invoice_months()
    cutoff = _iso_days_ago(months * 30.0)
    cur = conn.execute(
        "DELETE FROM invoices WHERE issue_date IS NULL OR issue_date < ?", (cutoff,)
    )
    return {"deleted_invoices": cur.rowcount}


def _run_unconfirmed(conn) -> dict:
    """Permanently delete accounts that were never confirmed after N hours.

    Only users who never confirmed their email (a confirm_token is still set)
    are removed, so manually-disabled confirmed users are never affected.
    """
    hours = unconfirmed_hours()
    cutoff = _iso_seconds_ago(hours)
    cur = conn.execute(
        "DELETE FROM users WHERE is_active = 0 AND confirm_token IS NOT NULL "
        "AND created_at < ?",
        (cutoff,),
    )
    return {"deleted_unconfirmed": cur.rowcount}


def _run_deactivated(conn) -> dict:
    """Permanently delete users whose deactivation grace period has passed.

    This runs on every maintenance pass regardless of the retention toggle,
    because the deletion was explicitly requested by the user (GDPR erase).
    """
    now = datetime.now().isoformat()
    rows = conn.execute(
        "SELECT id FROM users WHERE deactivated = 1 AND delete_after IS NOT NULL "
        "AND delete_after <= ?",
        (now,),
    ).fetchall()
    deleted = 0
    for row in rows:
        _delete_user(conn, row["id"])
        deleted += 1
    return {"deleted_deactivated": deleted}


def run_maintenance() -> dict:
    """Run all enabled cleanup jobs once. Returns a summary dict.

    User-requested deletions (deactivated accounts past their grace period) are
    always executed. The automated retention jobs (inactivity / old invoices /
    unconfirmed) only run when data retention is enabled in /admin.
    """
    result: dict = {"disabled": False}
    with _conn() as conn:
        # User-requested deletions (deactivated grace period) and unconfirmed
        # account cleanups are explicit business rules and always run.
        result["deactivated"] = _run_deactivated(conn)
        result["unconfirmed"] = _run_unconfirmed(conn)
        # Notification history older than 60 days is always pruned (bell feed).
        result["notifications"] = _run_old_notifications(conn)
        if not retention_enabled():
            result["disabled"] = True
        else:
            result["inactivity"] = _run_inactivity(conn)
            result["invoices"] = _run_invoices(conn)
    _LOGGER.info("Maintenance run: %s", result)
    return result


def _run_old_notifications(conn, days: int = 60) -> int:
    """Delete notification-history rows older than `days` days (bell feed)."""
    cur = conn.execute(
        "DELETE FROM notifications WHERE created_at < datetime('now', ?)",
        (f"-{int(days)} days",),
    )
    return cur.rowcount
