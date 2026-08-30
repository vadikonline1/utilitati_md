"""User notification delivery (email + Telegram) using admin-editable templates.

Both channels follow the user's profile preferences: the primary email, any
extra CC emails and Telegram chat ids. The message text comes from the admin
"Messages" tab (msg_type "invoices" for new invoices, "unpaid" for the monthly
unpaid summary); empty custom templates fall back to the built-in defaults in
``services.email``.
"""

from __future__ import annotations

from ..auth import get_user, get_user_lang
from . import email as email_svc
from . import telegram as telegram_svc
from .settings import parse_csv_list
from .utilities import get_home, get_notification_prefs, list_invoices

DEFAULT_LANG = "ro"


def _fmt(value) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _home_label(home: dict | None) -> str:
    if not home:
        return "—"
    name = (home.get("name") or "").strip()
    address = (home.get("address") or "").strip()
    if name and address:
        return f"{name} · {address}"
    return name or address or "—"


def invoice_lines(rows: list[dict]) -> list[str]:
    """Render one line per invoice: '• number — amount MDL'."""
    lines = []
    for row in rows:
        number = row.get("invoice_number") or "—"
        amount = _fmt(row.get("amount_mdl", 0))
        lines.append(f"  • {number} — {amount} MDL")
    return lines


def unpaid_lines(rows: list[dict]) -> list[str]:
    """Render one line per unpaid invoice including home + provider."""
    lines = []
    for row in rows:
        home = _home_label({
            "name": row.get("home_name"),
            "address": row.get("home_address"),
        })
        provider = row.get("provider") or row.get("account_label") or ""
        number = row.get("invoice_number") or "—"
        amount = _fmt(row.get("amount_mdl", 0))
        lines.append(f"  • {home} · {provider} · {number} — {amount} MDL")
    return lines


async def deliver_user_notification(user_id: int, msg_type: str, **kwargs) -> bool:
    """Send an admin-editable message to the user (email + Telegram per prefs)."""
    user = get_user(user_id) or {}
    prefs = get_notification_prefs(user_id)
    cc_emails = prefs.get("emails", "")
    chats = prefs.get("telegram", "")
    user_email = (user.get("email") or "").strip()
    if not user_email and not cc_emails and not chats:
        return False
    if "name" not in kwargs:
        kwargs["name"] = user.get("full_name") or user.get("username") or ""
    lang = get_user_lang(user_id) or DEFAULT_LANG
    subject, body = email_svc.render_template(msg_type, lang, **kwargs)

    delivered = False
    if user_email:
        delivered = email_svc.send_email(
            user_email, subject, body, cc=cc_emails or None
        ) or delivered
    else:
        for email in parse_csv_list(cc_emails):
            delivered = email_svc.send_email(email, subject, body) or delivered
    for chat in parse_csv_list(chats):
        await telegram_svc.send_message(chat, body)
        delivered = True
    return delivered


async def notify_new_invoices(
    user_id: int, account: dict, fetched, new_ids: list[int], site_url: str
) -> None:
    """Send the 'new invoices' message for a single account (editable template)."""
    if not new_ids:
        return
    new_ids_set = set(new_ids)
    rows = [
        inv for inv in list_invoices(user_id, account["id"]) if inv["id"] in new_ids_set
    ]
    if not rows:
        return
    total = sum(float(r.get("amount_mdl", 0) or 0) for r in rows)
    provider = getattr(fetched, "provider_name", None) or account.get(
        "label", account.get("provider", "")
    )
    home = get_home(user_id, account.get("home_id"))
    await deliver_user_notification(
        user_id,
        "invoices",
        home=_home_label(home),
        provider=provider,
        contract=account.get("contract_number", ""),
        count=len(rows),
        total=_fmt(total),
        invoices="\n".join(invoice_lines(rows)),
        site=site_url,
    )