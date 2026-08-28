"""JSON API routes: homes, accounts, invoices, providers, history, check."""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pyutilitati_md import (
    UtilitatiMDApiError,
    UtilitatiMDAuthError,
    UtilitatiMDConnectionError,
)

from ..deps import get_auth_token
from ..services.utilities import (
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
    data = await fetch_account_data(row)
    saved_ids = persist_invoices(account_id, data)
    return {
        "is_connected": data.is_connected,
        "error_message": data.error_message,
        "unpaid_balance_mdl": data.unpaid_balance_mdl,
        "invoice_count": len(saved_ids),
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
