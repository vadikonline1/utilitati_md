"""JSON API routes: homes, accounts, invoices, providers, history, check."""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pyutilitati_md import (
    UtilitatiMDApiError,
    UtilitatiMDAuthError,
    UtilitatiMDConnectionError,
)

from ..auth import (
    authenticate,
    change_password,
    create_invitation,
    create_session_token,
    deactivate_user,
    get_user,
    get_user_lang,
    register,
    resolve_reset_token,
    set_password_for_user,
    set_reset_token,
    set_user_full_name,
    user_by_email,
)
from ..config import SITE_URL
from ..deps import get_auth_token
from ..services import email as email_svc
from ..services import push as push_svc
from ..services import telegram as telegram_svc
from ..services.settings import admob_config
from ..services.utilities import (
    active_unpaid_balance,
    create_home,
    delete_account,
    delete_home,
    delete_invoice,
    fetch_account_data,
    get_account_row,
    get_home,
    get_invoice,
    list_accounts,
    list_homes,
    list_invoice_history,
    list_invoices,
    persist_invoices,
    set_account_status,
    set_home_status,
    set_invoice_status,
    submit_meter_reading,
    update_home,
    update_invoice,
    upsert_account,
)

router = APIRouter(prefix="/api")


def _iso(value):
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _public_user(user_id: int) -> dict | None:
    u = get_user(user_id)
    if u is None:
        return None
    return {
        "id": u["id"],
        "username": u["username"],
        "full_name": u.get("full_name") or "",
        "email": u.get("email") or "",
    }


# --------------------------------------------------------------------------- #
# Auth (JSON, used by the mobile app)
# --------------------------------------------------------------------------- #
@router.post("/auth/login")
async def auth_login(payload: dict):
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    user_id = authenticate(username, password)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Autentificare eșuată")
    return {"token": create_session_token(user_id), "user": _public_user(user_id)}


@router.post("/auth/register-invite")
async def auth_register_invite(payload: dict):
    """Register identical to the web flow: an email invitation (no password).

    The account is created inactive; after the user confirms the emailed link a
    password is generated and the account becomes active.
    """
    first_name = str(payload.get("first_name", "")).strip()
    last_name = str(payload.get("last_name", "")).strip()
    email = str(payload.get("email", "")).strip()
    username = str(payload.get("username", "")).strip()

    if not first_name or not last_name or not email or not username:
        raise HTTPException(status_code=400, detail="Completează toate câmpurile.")
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Adresa de email nu este validă.")

    full_name = f"{first_name} {last_name}".strip()
    lang = str(payload.get("lang", "ro") or "ro")[:2]
    if lang not in ("ro", "ru", "en"):
        lang = "ro"
    try:
        _, token = create_invitation(username, full_name, email)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))

    confirm_url = f"{SITE_URL}/confirm/{token}"
    email_svc.send_invitation(email, full_name, confirm_url, lang=lang)
    return {"sent": True, "email": email}


@router.post("/auth/register")
async def auth_register(payload: dict):
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    email = str(payload.get("email", "")).strip()
    full_name = str(payload.get("full_name", "")).strip()
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username și parola sunt obligatorii")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Parola trebuie să aibă minim 6 caractere")
    try:
        # Mobile self-service registration creates an active account directly.
        user_id = register(username, password, full_name, email, is_active=1)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    return {"token": create_session_token(user_id), "user": _public_user(user_id)}


@router.post("/devices/token")
async def device_token_register(
    payload: dict, user_id: int = Depends(get_auth_token)
):
    """Register a mobile push token ('fcm' firebase or 'expo') for a user."""
    token = str(payload.get("token", "")).strip()
    if not token or token == "ExponentPushToken[InvalidToken]":
        raise HTTPException(status_code=400, detail="Token invalid")
    platform = str(payload.get("platform", "android") or "android").lower()
    provider = str(payload.get("provider", "expo") or "expo").lower()
    push_svc.register_device_token(user_id, token, platform, provider)
    return {"registered": True}


@router.delete("/devices/token")
async def device_token_clear(user_id: int = Depends(get_auth_token)):
    """Remove all of the user's push tokens (notifications switched OFF)."""
    push_svc.clear_device_tokens(user_id)
    return {"cleared": True}


@router.post("/devices/test")
async def device_test_push(user_id: int = Depends(get_auth_token)):
    """Send a test push notification to the current user's devices."""
    sent = await push_svc.send_push(
        user_id,
        "Utilități.MD ✓",
        "Notificare de test — notificările sunt active.",
        type_="test",
    )
    if sent == 0:
        raise HTTPException(status_code=400, detail="Niciun token de notificare înregistrat")
    return {"sent": sent}


@router.get("/notifications")
async def get_notifications(user_id: int = Depends(get_auth_token)):
    """Most-recent notifications for the authenticated user (bell feed)."""
    return {"notifications": push_svc.list_user_notifications(user_id)}


@router.get("/config")
async def app_config(user_id: int = Depends(get_auth_token)):
    """Server-driven runtime config for the mobile app (e.g. AdMob)."""
    return {"admob": admob_config()}


@router.get("/auth/me")
async def auth_me(user_id: int = Depends(get_auth_token)):
    user = _public_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Utilizatorul nu a fost găsit")
    return user


@router.put("/auth/me")
async def auth_me_update(payload: dict, user_id: int = Depends(get_auth_token)):
    full_name = str(payload.get("full_name", "")).strip()
    if not full_name:
        raise HTTPException(status_code=400, detail="Numele complet nu poate fi gol")
    set_user_full_name(user_id, full_name)
    user = _public_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Utilizatorul nu a fost găsit")
    return user


@router.post("/auth/forgot-password")
async def auth_forgot_password(payload: dict):
    email = str(payload.get("email", "")).strip()
    user = user_by_email(email)
    if user:
        token = set_reset_token(user["id"])
        reset_url = f"{SITE_URL}/reset-password/{token}"
        lang = get_user_lang(user["id"]) or "ro"
        email_svc.send_reset_link(email, user.get("full_name", ""), reset_url, lang=lang)
        full = get_user(user["id"]) or {}
        chat_ids = full.get("telegram_chat_ids", "")
        if chat_ids:
            await telegram_svc.send_reset_link_to_chats(chat_ids, reset_url, lang)
    # Always return ok to avoid leaking which emails are registered.
    return {"ok": True}


@router.post("/auth/reset-password")
async def auth_reset_password(payload: dict):
    token = str(payload.get("token", "")).strip()
    new_password = str(payload.get("new_password", ""))
    user_id = resolve_reset_token(token)
    if user_id is None:
        raise HTTPException(status_code=400, detail="Linkul este invalid sau a expirat")
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Parola trebuie să aibă minim 6 caractere")
    set_password_for_user(user_id, new_password)
    return {"ok": True}


@router.post("/auth/change-password")
async def auth_change_password(payload: dict, user_id: int = Depends(get_auth_token)):
    old_password = str(payload.get("current_password", ""))
    new_password = str(payload.get("new_password", ""))
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Parola trebuie să aibă minim 6 caractere")
    if not change_password(user_id, old_password, new_password):
        raise HTTPException(status_code=400, detail="Parola actuală este incorectă")
    return {"ok": True}


@router.post("/auth/deactivate")
async def auth_deactivate(user_id: int = Depends(get_auth_token)):
    deactivate_user(user_id, days=30)
    return {"ok": True}


def _provider_error(err):
    if isinstance(err, UtilitatiMDAuthError):
        return HTTPException(status_code=401, detail=f"Autentificare eșuată: {err}")
    return HTTPException(status_code=502, detail=f"Eroare furnizor: {err}")


async def _get_account(user_id: int, account_id: int) -> dict:
    row = get_account_row(user_id, account_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Contul nu a fost găsit")
    return row


@router.get("/providers")
async def providers(user_id: int = Depends(get_auth_token)):
    from .pages import PROVIDER_META

    return [{"id": pid, **meta} for pid, meta in sorted(PROVIDER_META.items())]


# --------------------------------------------------------------------------- #
# Homes
# --------------------------------------------------------------------------- #
@router.get("/homes")
async def homes(user_id: int = Depends(get_auth_token)):
    return list_homes(user_id)


@router.post("/homes")
async def create_home_api(payload: dict, user_id: int = Depends(get_auth_token)):
    home_id = create_home(user_id, payload)
    home = get_home(user_id, home_id)
    if home is None:
        raise HTTPException(status_code=500, detail="Nu s-a putut crea locuința")
    return home


@router.get("/homes/{home_id}")
async def home_detail(home_id: int, user_id: int = Depends(get_auth_token)):
    home = get_home(user_id, home_id)
    if home is None:
        raise HTTPException(status_code=404, detail="Locuința nu a fost găsită")
    return {"home": home, "accounts": list_accounts(user_id, home_id)}


@router.put("/homes/{home_id}")
async def home_update(home_id: int, payload: dict, user_id: int = Depends(get_auth_token)):
    if not update_home(user_id, home_id, payload):
        raise HTTPException(status_code=404, detail="Locuința nu a fost găsită")
    return get_home(user_id, home_id)


@router.post("/homes/{home_id}/status")
async def home_status(home_id: int, status: str = Query(...), user_id: int = Depends(get_auth_token)):
    if not set_home_status(user_id, home_id, status):
        raise HTTPException(status_code=404, detail="Locuința nu a fost găsită")
    return get_home(user_id, home_id)


@router.delete("/homes/{home_id}")
async def home_delete(home_id: int, user_id: int = Depends(get_auth_token)):
    if not delete_home(user_id, home_id):
        raise HTTPException(
            status_code=400,
            detail="Ștergerea e permisă doar pentru locuințe dezactivate (disabled).",
        )
    return {"deleted": True}


# --------------------------------------------------------------------------- #
# Accounts (utilities)
# --------------------------------------------------------------------------- #
@router.get("/accounts")
async def accounts(
    home_id: int | None = None, user_id: int = Depends(get_auth_token)
):
    return list_accounts(user_id, home_id)


@router.post("/accounts")
async def create_account(payload: dict, user_id: int = Depends(get_auth_token)):
    account_id = upsert_account(user_id, payload)
    row = get_account_row(user_id, account_id)
    if row is None:
        raise HTTPException(status_code=500, detail="Nu s-a putut crea contul")
    return row


@router.get("/accounts/{account_id}")
async def account_detail(account_id: int, user_id: int = Depends(get_auth_token)):
    return await _get_account(user_id, account_id)


@router.put("/accounts/{account_id}")
async def account_update(
    account_id: int, payload: dict, user_id: int = Depends(get_auth_token)
):
    await _get_account(user_id, account_id)
    upsert_account(user_id, payload, account_id=account_id)
    return get_account_row(user_id, account_id)


@router.post("/accounts/{account_id}/status")
async def account_status(
    account_id: int, status: str = Query(...), user_id: int = Depends(get_auth_token)
):
    await _get_account(user_id, account_id)
    if not set_account_status(user_id, account_id, status):
        raise HTTPException(status_code=404, detail="Contul nu a fost găsit")
    return get_account_row(user_id, account_id)


@router.delete("/accounts/{account_id}")
async def account_delete(account_id: int, user_id: int = Depends(get_auth_token)):
    await _get_account(user_id, account_id)
    if not delete_account(user_id, account_id):
        raise HTTPException(status_code=404, detail="Contul nu a fost găsit")
    return {"deleted": True}


@router.get("/accounts/{account_id}/invoices")
async def account_invoices(account_id: int, user_id: int = Depends(get_auth_token)):
    await _get_account(user_id, account_id)
    return {"invoices": list_invoices(user_id, account_id)}


@router.post("/accounts/{account_id}/refresh")
async def account_refresh(account_id: int, user_id: int = Depends(get_auth_token)):
    row = await _get_account(user_id, account_id)
    prev_balance = active_unpaid_balance(account_id)
    data = await fetch_account_data(row)
    _created, saved_ids = persist_invoices(account_id, data)
    new_balance = active_unpaid_balance(account_id) if data.is_connected else prev_balance
    return {
        "is_connected": data.is_connected,
        "error_message": data.error_message,
        "unpaid_balance_mdl": data.unpaid_balance_mdl,
        "invoice_count": len(saved_ids),
        "created_count": len(_created),
        "balance_increased": bool(new_balance > prev_balance),
        "invoices": _serialize_invoices(data),
        "last_invoice": _serialize_provider_invoice(data.last_invoice),
    }


@router.post("/accounts/{account_id}/meter-reading")
async def meter_reading(
    account_id: int,
    reading_value: float = Query(...),
    user_id: int = Depends(get_auth_token),
):
    row = await _get_account(user_id, account_id)
    try:
        ok = await submit_meter_reading(row, reading_value)
    except (UtilitatiMDAuthError, UtilitatiMDConnectionError, UtilitatiMDApiError) as err:
        raise _provider_error(err)
    return {"submitted": ok}


# --------------------------------------------------------------------------- #
# Invoices + history
# --------------------------------------------------------------------------- #
@router.get("/invoices")
async def invoices(
    account_id: int | None = None, user_id: int = Depends(get_auth_token)
):
    return {"invoices": list_invoices(user_id, account_id)}


@router.get("/invoices/{invoice_id}/history")
async def invoice_history(
    invoice_id: int, user_id: int = Depends(get_auth_token)
):
    if get_invoice(user_id, invoice_id) is None:
        raise HTTPException(status_code=404, detail="Factura nu a fost găsită")
    return {"history": list_invoice_history(user_id, invoice_id)}


@router.put("/invoices/{invoice_id}")
async def invoice_update(
    invoice_id: int, payload: dict, user_id: int = Depends(get_auth_token)
):
    if not update_invoice(user_id, invoice_id, payload):
        raise HTTPException(status_code=404, detail="Factura nu a fost găsită")
    return get_invoice(user_id, invoice_id)


@router.post("/invoices/{invoice_id}/status")
async def invoice_status(
    invoice_id: int, status: str = Query(...), user_id: int = Depends(get_auth_token)
):
    if not set_invoice_status(user_id, invoice_id, status):
        raise HTTPException(status_code=404, detail="Factura nu a fost găsită")
    return get_invoice(user_id, invoice_id)


@router.delete("/invoices/{invoice_id}")
async def invoice_delete(invoice_id: int, user_id: int = Depends(get_auth_token)):
    if not delete_invoice(user_id, invoice_id):
        raise HTTPException(status_code=404, detail="Factura nu a fost găsită")
    return {"deleted": True}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _serialize_provider_invoice(inv):
    if inv is None:
        return None
    return {
        "invoice_number": inv.invoice_number,
        "amount_mdl": inv.amount_mdl,
        "currency": inv.currency,
        "period": inv.period,
        "issue_date": _iso(inv.issue_date),
        "due_date": _iso(inv.due_date),
        "is_paid": inv.is_paid,
        "status": inv.status,
        "external_invoice_id": inv.external_invoice_id,
        "pdf_url": inv.pdf_url,
        "checked_at": _iso(inv.checked_at),
    }


def _serialize_invoices(data):
    invoices = getattr(data, "invoices", None)
    if not invoices:
        return []
    return [_serialize_provider_invoice(inv) for inv in invoices]
