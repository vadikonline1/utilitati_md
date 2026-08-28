"""Page routes (HTML rendering): landing, auth, dashboard, homes, invoices."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth import authenticate, change_password, create_session_token, register
from ..config import TEMPLATES_DIR
from ..deps import optional_auth_token
from ..i18n import LANG_NAMES, LANGS, get_lang, make_translator
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
    update_home,
    update_invoice,
    upsert_account,
)

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

PROVIDER_META = {
    "premier_energy": {"icon": "⚡", "name": "Premier Energy", "fields": ["contract", "username", "password"]},
    "infosapr": {"icon": "💧", "name": "InfoSapr", "fields": ["contract"]},
    "energocom": {"icon": "⚡", "name": "Energocom", "fields": ["contract"]},
    "starnet": {"icon": "🌐", "name": "Starnet", "fields": ["contract"]},
    "fee_nord": {"icon": "⚡", "name": "FEE Nord", "fields": ["contract"]},
    "apa_canal_chisinau": {"icon": "💧", "name": "Apă-Canal Chișinău", "fields": ["contract"]},
    "auto_salubritate": {"icon": "🗑", "name": "Auto Salubritate", "fields": ["contract"]},
    "termoelectrica": {"icon": "🔥", "name": "Termoelectrica", "fields": ["contract"]},
    "infocom": {"icon": "📡", "name": "INFOCOM", "fields": ["contract"]},
    "stroy_master_domofon": {"icon": "🚪", "name": "Stroy Master Domofon", "fields": ["contract"]},
}


def _ctx(request, **extra):
    lang = get_lang(request.cookies.get("lang"))
    ctx = {
        "request": request,
        "now": datetime.now(),
        "providers": PROVIDER_META,
        "lang": lang,
        "t": make_translator(lang),
        "langs": LANG_NAMES,
    }
    ctx.update(extra)
    return ctx


# --------------------------------------------------------------------------- #
# Public landing page
# --------------------------------------------------------------------------- #
@router.get("/", response_class=HTMLResponse)
async def home(request: Request, user_id: int | None = Depends(optional_auth_token)):
    return templates.TemplateResponse(
        request, "home.html", _ctx(request, logged_in=user_id is not None)
    )


# --------------------------------------------------------------------------- #
# Language switch
# --------------------------------------------------------------------------- #
@router.get("/set-language/{lang}")
async def set_language(
    lang: str, request: Request, user_id: int | None = Depends(optional_auth_token)
):
    back = request.query_params.get("next")
    if not back or not back.startswith("/") or back.startswith("//"):
        back = "/dashboard" if user_id else "/"
    response = RedirectResponse(str(back), status_code=303)
    if lang in LANGS:
        response.set_cookie("lang", lang, samesite="lax")
    return response


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, user_id: int | None = Depends(optional_auth_token)):
    if user_id is not None:
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(request, "login.html", _ctx(request, error=None))


@router.post("/login")
async def login_submit(request: Request):
    form = await request.form()
    username = str(form.get("username", ""))
    password = str(form.get("password", ""))
    user_id = authenticate(username, password)
    if user_id is None:
        _t = make_translator(get_lang(request.cookies.get("lang")))
        return templates.TemplateResponse(
            request, "login.html", _ctx(request, error=_t("login_invalid")),
            status_code=401,
        )
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie("session", create_session_token(user_id), httponly=True)
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, user_id: int | None = Depends(optional_auth_token)):
    if user_id is not None:
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(request, "register.html", _ctx(request, error=None))


@router.post("/register")
async def register_submit(request: Request):
    form = await request.form()
    _t = make_translator(get_lang(request.cookies.get("lang")))
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))
    confirm = str(form.get("confirm", ""))
    if not username or not password:
        return templates.TemplateResponse(
            request, "register.html",
            _ctx(request, error=_t("register_fill")), status_code=400,
        )
    if password != confirm:
        return templates.TemplateResponse(
            request, "register.html",
            _ctx(request, error=_t("register_mismatch")), status_code=400,
        )
    try:
        user_id = register(username, password)
    except ValueError:
        return templates.TemplateResponse(
            request, "register.html",
            _ctx(request, error=_t("register_taken")), status_code=400,
        )
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie("session", create_session_token(user_id), httponly=True)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("session")
    return response


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, user_id: int | None = Depends(optional_auth_token)):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "profile.html", _ctx(request, message=None))


@router.post("/profile")
async def profile_submit(request: Request, user_id: int | None = Depends(optional_auth_token)):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    _t = make_translator(get_lang(request.cookies.get("lang")))
    form = await request.form()
    old = str(form.get("old_password", ""))
    new = str(form.get("new_password", ""))
    confirm = str(form.get("confirm", ""))
    if new != confirm:
        return templates.TemplateResponse(
            request, "profile.html", _ctx(request, message=_t("profile_mismatch")),
        )
    if change_password(user_id, old, new):
        return templates.TemplateResponse(
            request, "profile.html", _ctx(request, message=_t("profile_changed")),
        )
    return templates.TemplateResponse(
        request, "profile.html", _ctx(request, message=_t("profile_wrong_old")),
    )


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user_id: int | None = Depends(optional_auth_token)):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request, "dashboard.html", _ctx(request, homes=list_homes(user_id)),
    )


# --------------------------------------------------------------------------- #
# Homes
# --------------------------------------------------------------------------- #
@router.get("/homes", response_class=HTMLResponse)
async def homes_page(request: Request, user_id: int | None = Depends(optional_auth_token)):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request, "homes.html", _ctx(request, homes=list_homes(user_id)),
    )


@router.post("/homes")
async def homes_create(request: Request, user_id: int | None = Depends(optional_auth_token)):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    create_home(user_id, {
        "name": form.get("name", ""),
        "address": form.get("address", ""),
        "floor": form.get("floor", ""),
        "metro_area": form.get("metro_area", ""),
    })
    return RedirectResponse("/homes", status_code=303)


@router.get("/homes/{home_id}", response_class=HTMLResponse)
async def home_detail_page(
    home_id: int, request: Request, user_id: int | None = Depends(optional_auth_token)
):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    home = get_home(user_id, home_id)
    if home is None:
        return RedirectResponse("/homes", status_code=303)
    return templates.TemplateResponse(
        request, "home_detail.html",
        _ctx(request, home=home, accounts=list_accounts(user_id, home_id)),
    )


@router.post("/homes/{home_id}/edit")
async def home_edit_submit(
    home_id: int, request: Request, user_id: int | None = Depends(optional_auth_token)
):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    update_home(user_id, home_id, {
        "name": form.get("name", ""),
        "address": form.get("address", ""),
        "floor": form.get("floor", ""),
        "metro_area": form.get("metro_area", ""),
        "status": form.get("status", "enabled"),
    })
    return RedirectResponse(f"/homes/{home_id}", status_code=303)


@router.post("/homes/{home_id}/status")
async def home_status_submit(
    home_id: int, request: Request, user_id: int | None = Depends(optional_auth_token)
):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    set_home_status(user_id, home_id, str(form.get("status", "enabled")))
    return RedirectResponse(f"/homes/{home_id}", status_code=303)


@router.post("/homes/{home_id}/delete")
async def home_delete_submit(
    home_id: int, request: Request, user_id: int | None = Depends(optional_auth_token)
):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    if str(form.get("confirm", "")) == "yes":
        delete_home(user_id, home_id)
    return RedirectResponse("/homes", status_code=303)


# --------------------------------------------------------------------------- #
# Utility (account) connect / manage within a home
# --------------------------------------------------------------------------- #
@router.post("/homes/{home_id}/utilities")
async def utility_connect(
    home_id: int, request: Request, user_id: int | None = Depends(optional_auth_token)
):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    provider = str(form.get("provider", ""))
    contract_number = str(form.get("contract_number", ""))
    if not provider or not contract_number:
        return RedirectResponse(f"/homes/{home_id}", status_code=303)

    meta = PROVIDER_META.get(provider, {})
    fields = meta.get("fields", ["contract"])
    data = {
        "home_id": home_id,
        "provider": provider,
        "label": meta.get("name", provider),
        "contract_number": contract_number,
        "icon": meta.get("icon", "📄"),
        "username": None,
        "password": None,
        "place_of_consumption": None,
    }
    if "username" in fields:
        data["username"] = form.get("username") or None
    if "password" in fields:
        data["password"] = form.get("password") or None

    # StarNet: the contract number is also the personal-cabinet login (ID).
    if provider == "starnet":
        data["username"] = data["username"] or contract_number

    acc_id = upsert_account(user_id, data)
    new_account = get_account_row(user_id, acc_id)
    if new_account is not None:
        fetched = await fetch_account_data(new_account)
        persist_invoices(acc_id, fetched)
    return RedirectResponse(f"/homes/{home_id}?added={acc_id}", status_code=303)


@router.post("/homes/{home_id}/utilities/{account_id}/status")
async def utility_status_submit(
    home_id: int, account_id: int, request: Request,
    user_id: int | None = Depends(optional_auth_token),
):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    set_account_status(user_id, account_id, str(form.get("status", "enabled")))
    return RedirectResponse(f"/homes/{home_id}", status_code=303)


@router.post("/homes/{home_id}/utilities/{account_id}/delete")
async def utility_delete_submit(
    home_id: int, account_id: int, request: Request,
    user_id: int | None = Depends(optional_auth_token),
):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    delete_account(user_id, account_id)
    return RedirectResponse(f"/homes/{home_id}", status_code=303)


# --------------------------------------------------------------------------- #
# Invoices (per account)
# --------------------------------------------------------------------------- #
@router.get("/accounts/{account_id}/invoices", response_class=HTMLResponse)
async def invoice_page(
    account_id: int, request: Request, user_id: int | None = Depends(optional_auth_token)
):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    account = get_account_row(user_id, account_id)
    if account is None:
        return RedirectResponse("/dashboard", status_code=303)
    invoices = list_invoices(user_id, account_id)
    if not invoices:
        data = await fetch_account_data(account)
        persist_invoices(account_id, data)
        invoices = list_invoices(user_id, account_id)
    history = (
        list_invoice_history(user_id, invoices[0]["id"]) if invoices else []
    )
    return templates.TemplateResponse(
        request, "invoices.html",
        _ctx(
            request,
            account=account,
            invoices=invoices,
            history=history,
            provider_meta=PROVIDER_META.get(account["provider"], {}),
            refresh_error=None,
        ),
    )


@router.post("/accounts/{account_id}/invoices/refresh")
async def invoice_refresh(
    account_id: int, request: Request, user_id: int | None = Depends(optional_auth_token)
):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    account = get_account_row(user_id, account_id)
    if account is None:
        return RedirectResponse("/dashboard", status_code=303)
    data = await fetch_account_data(account)
    error = None
    persist_invoices(account_id, data)
    if not data.is_connected:
        error = data.error_message
    invoices = list_invoices(user_id, account_id)
    history = (
        list_invoice_history(user_id, invoices[0]["id"]) if invoices else []
    )
    return templates.TemplateResponse(
        request, "invoices.html",
        _ctx(
            request,
            account=account,
            invoices=invoices,
            history=history,
            provider_meta=PROVIDER_META.get(account["provider"], {}),
            refresh_error=error,
        ),
    )


@router.get("/invoices", response_class=HTMLResponse)
async def invoices_all_page(
    request: Request,
    home_id: int | None = None,
    user_id: int | None = Depends(optional_auth_token),
):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    accounts = list_accounts(user_id, home_id=home_id)
    current_home = get_home(user_id, home_id) if home_id else None
    return templates.TemplateResponse(
        request, "invoices_all.html",
        _ctx(
            request,
            invoices=list_invoices(user_id, home_id=home_id),
            accounts=accounts,
            homes=list_homes(user_id),
            current_home=current_home,
        ),
    )


@router.post("/invoices/{invoice_id}/status")
async def invoice_status_submit(
    invoice_id: int, request: Request,
    user_id: int | None = Depends(optional_auth_token),
):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    inv = get_invoice(user_id, invoice_id)
    if inv is not None:
        set_invoice_status(user_id, invoice_id, str(form.get("status", "enabled")))
        return RedirectResponse(
            str(form.get("back", f"/accounts/{inv['account_id']}/invoices")),
            status_code=303,
        )
    return RedirectResponse("/invoices", status_code=303)


@router.post("/invoices/{invoice_id}/edit")
async def invoice_edit_submit(
    invoice_id: int, request: Request,
    user_id: int | None = Depends(optional_auth_token),
):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    inv = get_invoice(user_id, invoice_id)
    if inv is not None:
        update_invoice(user_id, invoice_id, {
            "amount_mdl": form.get("amount_mdl", inv["amount_mdl"] or 0),
            "issue_date": form.get("issue_date") or None,
            "due_date": form.get("due_date") or None,
            "is_paid": bool(form.get("is_paid")),
        })
        return RedirectResponse(
            str(form.get("back", f"/accounts/{inv['account_id']}/invoices")),
            status_code=303,
        )
    return RedirectResponse("/invoices", status_code=303)


@router.post("/invoices/{invoice_id}/delete")
async def invoice_delete_submit(
    invoice_id: int, request: Request,
    user_id: int | None = Depends(optional_auth_token),
):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    inv = get_invoice(user_id, invoice_id)
    if inv is not None:
        delete_invoice(user_id, invoice_id)
        return RedirectResponse(
            str(form.get("back", f"/accounts/{inv['account_id']}/invoices")),
            status_code=303,
        )
    return RedirectResponse("/invoices", status_code=303)
