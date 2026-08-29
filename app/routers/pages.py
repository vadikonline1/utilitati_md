"""Page routes (HTML rendering): landing, auth, dashboard, homes, invoices."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth import (
    authenticate,
    change_password,
    confirm_invitation,
    create_invitation,
    create_session_token,
    get_user,
    get_user_lang,
    parse_session_token,
    register,
    resolve_reset_token,
    set_password_for_user,
    set_reset_token,
    set_user_lang,
    user_by_email,
)
from ..config import is_admin_username, SITE_URL, TEMPLATES_DIR
from ..deps import optional_auth_token
from ..i18n import LANG_NAMES, LANGS, get_lang, make_translator
from ..services import email as email_svc
from ..services.settings import (
    MSG_TYPES,
    all_settings,
    get_setting,
    get_sync_interval_hours,
    inactive_months,
    invoice_months,
    msg_templates,
    retention_enabled,
    set_msg_templates,
    set_settings,
    unconfirmed_hours,
    warn_days,
)
from ..services.sync import dashboard_stats, generate_invoices_for_user
from ..services.utilities import (
    create_home,
    delete_account,
    delete_home,
    delete_invoice,
    fetch_account_data,
    get_account_row,
    get_home,
    get_invoice,
    get_notification_prefs,
    get_username,
    list_accounts,
    list_homes,
    list_invoice_history,
    list_invoices,
    persist_invoices,
    set_account_status,
    set_home_status,
    set_invoice_status,
    set_notification_prefs,
    update_home,
    update_invoice,
    upsert_account,
)

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _email_cfg() -> bool:
    """True when SMTP is configured in /admin (email notifications available)."""
    return email_svc.smtp_configured()


def _telegram_cfg() -> bool:
    """True when a Telegram bot token is configured in /admin."""
    return bool(get_setting("telegram_token"))


def _telegram_bot_url() -> str:
    """Human-readable URL of our Telegram bot (t.me/<botname>)."""
    botname = get_setting("telegram_botname", "utilitati_md_bot").strip().lstrip("@")
    return f"https://t.me/{botname}"

PROVIDER_META = {
    "infosapr": {"icon": "💧", "name": "InfoSapr", "fields": ["contract"], "account_label": "Numărul contului personal", "placeholder": "ex: 123456789"},
    "premier_energy": {"icon": "⚡", "name": "Premier Energy", "fields": ["contract"], "account_label": "Cod NLC", "placeholder": "ex: 123456789"},
    "energocom": {"icon": "🔥", "name": "Energocom", "fields": ["contract"], "account_label": "Contul personal", "placeholder": "14 caractere (ex: 123/0123456789)"},
    "infocom": {"icon": "📡", "name": "INFOCOM", "fields": ["contract"], "account_label": "Numărul contului", "placeholder": "ex: 123456"},
    "termoelectrica": {"icon": "🔥", "name": "Termoelectrica", "fields": ["contract"], "account_label": "Numărul contului", "placeholder": "14 cifre (ex: 12345678901234)"},
    "apa_canal_chisinau": {"icon": "💧", "name": "Apă-Canal Chișinău", "fields": ["contract"], "account_label": "Numărul contului", "placeholder": "5-9 caractere (A, P, cifre)"},
    "starnet": {"icon": "🌐", "name": "StarNet", "fields": ["contract"], "account_label": "Codul personal", "placeholder": "1-12 cifre"},
    "fee_nord": {"icon": "⚡", "name": "FEE Nord", "fields": ["contract"], "account_label": "Numărul contractului", "placeholder": "ex: 12-1234567890"},
    "stroy_master_domofon": {"icon": "🚪", "name": "Stroy Master Domofon", "fields": ["contract"], "account_label": "Cont Abonat", "placeholder": "ex: 123456"},
}


def _ctx(request, **extra):
    uid = parse_session_token(request.cookies.get("session") or "")
    # Per-user platform language takes priority over the browser/cookie choice.
    lang = get_user_lang(uid) if uid is not None else None
    if lang is None:
        lang = get_lang(request.cookies.get("lang"))
    ctx = {
        "request": request,
        "now": datetime.now(),
        "providers": PROVIDER_META,
        "lang": lang,
        "t": make_translator(lang),
        "langs": LANG_NAMES,
        "logged_in": uid is not None,
        "is_admin": uid is not None and is_admin_username(get_username(uid)),
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
        # Remember the user's preferred platform language on their profile.
        if user_id is not None:
            set_user_lang(user_id, lang)
    return response


# --------------------------------------------------------------------------- #
# Legal / contact public pages
# --------------------------------------------------------------------------- #
@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request, user_id: int | None = Depends(optional_auth_token)):
    return templates.TemplateResponse(
        request, "privacy.html",
        _ctx(request, logged_in=user_id is not None),
    )


@router.get("/contact", response_class=HTMLResponse)
async def contact_page(request: Request, user_id: int | None = Depends(optional_auth_token)):
    return templates.TemplateResponse(
        request, "contact.html",
        _ctx(request, logged_in=user_id is not None),
    )


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
    _t = make_translator(get_lang(request.cookies.get("lang")))
    form = await request.form()
    first_name = str(form.get("first_name", "")).strip()
    last_name = str(form.get("last_name", "")).strip()
    email = str(form.get("email", "")).strip()
    username = str(form.get("username", "")).strip()

    if not first_name or not last_name or not email or not username:
        return templates.TemplateResponse(
            request, "register.html",
            _ctx(request, error=_t("register_fill")), status_code=400,
        )
    if "@" not in email or "." not in email.split("@")[-1]:
        return templates.TemplateResponse(
            request, "register.html",
            _ctx(request, error=_t("register_bad_email")), status_code=400,
        )
    full_name = f"{first_name} {last_name}".strip()
    try:
        _, token = create_invitation(username, full_name, email)
    except ValueError:
        return templates.TemplateResponse(
            request, "register.html",
            _ctx(request, error=_t("register_taken")), status_code=400,
        )

    confirm_url = f"{SITE_URL}/confirm/{token}"
    email_svc.send_invitation(
        email, full_name, confirm_url,
        lang=get_lang(request.cookies.get("lang")),
    )

    return templates.TemplateResponse(
        request, "register.html",
        _ctx(request, sent=_t("register_sent")),
    )


@router.get("/confirm/{token}", response_class=HTMLResponse)
async def confirm_page(token: str, request: Request):
    _t = make_translator(get_lang(request.cookies.get("lang")))
    result = confirm_invitation(token)
    if result is None:
        return templates.TemplateResponse(
            request, "confirm.html",
            _ctx(request, ok=False, message=_t("confirm_invalid")),
        )
    user_id, generated_password = result
    user = get_user(user_id)
    if user and user.get("email"):
        email_svc.send_welcome(
            user["email"], user.get("full_name", ""), user.get("username", ""),
            generated_password,
            lang=get_user_lang(user_id) or get_lang(request.cookies.get("lang")),
        )
    return templates.TemplateResponse(
        request, "confirm.html",
        _ctx(request, ok=True, message=_t("confirm_ok")),
    )


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(
    request: Request, user_id: int | None = Depends(optional_auth_token)
):
    if user_id is not None:
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(
        request, "forgot_password.html", _ctx(request, message=None),
    )


@router.post("/forgot-password")
async def forgot_password_submit(request: Request):
    _t = make_translator(get_lang(request.cookies.get("lang")))
    form = await request.form()
    email = str(form.get("email", "")).strip()
    user = user_by_email(email)
    if user:
        token = set_reset_token(user["id"])
        reset_url = f"{SITE_URL}/reset-password/{token}"
        email_svc.send_reset_link(
            email, user.get("full_name", ""), reset_url,
            lang=get_user_lang(user["id"]) or get_lang(request.cookies.get("lang")),
        )
    # Always show the same message to avoid leaking which emails are registered.
    return templates.TemplateResponse(
        request, "forgot_password.html",
        _ctx(request, message=_t("forgot_sent")),
    )


@router.get("/reset-password/{token}", response_class=HTMLResponse)
async def reset_password_page(token: str, request: Request):
    _t = make_translator(get_lang(request.cookies.get("lang")))
    user_id = resolve_reset_token(token)
    if user_id is None:
        return templates.TemplateResponse(
            request, "reset_password.html",
            _ctx(request, token=None, error=_t("reset_invalid")),
        )
    return templates.TemplateResponse(
        request, "reset_password.html", _ctx(request, token=token, error=None),
    )


@router.post("/reset-password/{token}")
async def reset_password_submit(token: str, request: Request):
    _t = make_translator(get_lang(request.cookies.get("lang")))
    user_id = resolve_reset_token(token)
    if user_id is None:
        return templates.TemplateResponse(
            request, "reset_password.html",
            _ctx(request, token=None, error=_t("reset_invalid")),
        )
    form = await request.form()
    new_password = str(form.get("password", ""))
    confirm = str(form.get("confirm", ""))
    if len(new_password) < 6:
        return templates.TemplateResponse(
            request, "reset_password.html",
            _ctx(request, token=token, error=_t("reset_weak")),
        )
    if new_password != confirm:
        return templates.TemplateResponse(
            request, "reset_password.html",
            _ctx(request, token=token, error=_t("reset_mismatch")),
        )
    set_password_for_user(user_id, new_password)
    return templates.TemplateResponse(
        request, "reset_password.html",
        _ctx(request, token=None, done=True, error=None),
    )


@router.get("/logout")
async def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("session")
    return response


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, user_id: int | None = Depends(optional_auth_token)):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    prefs = get_notification_prefs(user_id)
    return templates.TemplateResponse(
        request, "profile.html",
        _ctx(
            request,
            message=None,
            username=get_username(user_id),
            user_lang=get_user_lang(user_id) or lang,
            emails=prefs["emails"],
            telegram_chat_ids=prefs["telegram"],
            email_configured=_email_cfg(),
            telegram_configured=_telegram_cfg(),
            telegram_bot_url=_telegram_bot_url(),
            is_admin=_is_admin(user_id),
        ),
    )


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


@router.post("/profile/notifications")
async def profile_notifications_submit(
    request: Request, user_id: int | None = Depends(optional_auth_token)
):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    _t = make_translator(get_lang(request.cookies.get("lang")))
    form = await request.form()
    set_notification_prefs(
        user_id,
        str(form.get("emails", "")),
        str(form.get("telegram_chat_ids", "")),
    )
    prefs = get_notification_prefs(user_id)
    return templates.TemplateResponse(
        request, "profile.html",
        _ctx(
            request,
            message=_t("profile_notif_saved"),
            username=get_username(user_id),
            user_lang=get_user_lang(user_id) or lang,
            emails=prefs["emails"],
            telegram_chat_ids=prefs["telegram"],
            email_configured=_email_cfg(),
            telegram_configured=_telegram_cfg(),
            telegram_bot_url=_telegram_bot_url(),
            is_admin=_is_admin(user_id),
        ),
    )


@router.post("/profile/language")
async def profile_language_submit(
    request: Request, user_id: int | None = Depends(optional_auth_token)
):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    lang = str(form.get("lang", "")).strip()
    if lang in LANGS:
        set_user_lang(user_id, lang)
    response = RedirectResponse("/profile", status_code=303)
    response.set_cookie("lang", lang if lang in LANGS else "ro", samesite="lax")
    return response


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user_id: int | None = Depends(optional_auth_token)):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request, "dashboard.html",
        _ctx(
            request,
            homes=list_homes(user_id),
            stats=dashboard_stats(user_id),
        ),
    )


# --------------------------------------------------------------------------- #
# Admin dashboard (SMTP / Telegram / sync settings)
# --------------------------------------------------------------------------- #
def _is_admin(user_id: int | None) -> bool:
    return user_id is not None and is_admin_username(get_username(user_id))


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, user_id: int | None = Depends(optional_auth_token)):
    _t = make_translator(get_lang(request.cookies.get("lang")))
    if not _is_admin(user_id):
        return templates.TemplateResponse(
            request, "admin.html",
            _ctx(request, denied=True, message=_t("admin_not_admin")),
        )
    return templates.TemplateResponse(
        request, "admin.html",
        _ctx(
            request,
            denied=False,
            settings=all_settings(),
            retention_enabled=retention_enabled(),
            inactive_months=inactive_months(),
            warn_days_list=warn_days(),
            invoice_months=invoice_months(),
            unconfirmed_hours=unconfirmed_hours(),
            msg_types=MSG_TYPES,
            msg_templates_data={mt: msg_templates(mt) for mt in MSG_TYPES},
        ),
    )


@router.post("/admin")
async def admin_submit(request: Request, user_id: int | None = Depends(optional_auth_token)):
    _t = make_translator(get_lang(request.cookies.get("lang")))
    if not _is_admin(user_id):
        return templates.TemplateResponse(
            request, "admin.html",
            _ctx(request, denied=True, message=_t("admin_not_admin")),
        )
    form = await request.form()
    sync_mode = str(form.get("sync_mode", "daily"))
    sync_hours = form.get("sync_hours", "24")
    values = {
        "smtp_host": str(form.get("smtp_host", "")),
        "smtp_port": str(form.get("smtp_port", "")),
        "smtp_user": str(form.get("smtp_user", "")),
        "smtp_pass": str(form.get("smtp_pass", "")),
        "smtp_from": str(form.get("smtp_from", "")),
        "telegram_token": str(form.get("telegram_token", "")),
        "telegram_botname": str(form.get("telegram_botname", "")),
        "sync_mode": sync_mode,
        "retention_enabled": "1" if form.get("retention_enabled") else "0",
        "inactive_months": str(form.get("inactive_months", "12")),
        "warn_days": str(form.get("warn_days", "90,60,30")),
        "invoice_months": str(form.get("invoice_months", "24")),
        "unconfirmed_hours": str(form.get("unconfirmed_hours", "24")),
    }
    if sync_mode == "interval":
        try:
            values["sync_hours"] = str(max(1, min(168, int(float(sync_hours)))))
        except (TypeError, ValueError):
            values["sync_hours"] = "24"
    set_settings(values)
    return templates.TemplateResponse(
        request, "admin.html",
        _ctx(
            request,
            denied=False,
            message=_t("admin_saved"),
            settings=all_settings(),
            retention_enabled=retention_enabled(),
            inactive_months=inactive_months(),
            warn_days_list=warn_days(),
            invoice_months=invoice_months(),
            unconfirmed_hours=unconfirmed_hours(),
            msg_types=MSG_TYPES,
            msg_templates_data={mt: msg_templates(mt) for mt in MSG_TYPES},
        ),
    )


@router.post("/admin/messages/{msg_type}")
async def admin_messages_submit(
    msg_type: str, request: Request, user_id: int | None = Depends(optional_auth_token)
):
    _t = make_translator(get_lang(request.cookies.get("lang")))
    if not _is_admin(user_id):
        return templates.TemplateResponse(
            request, "admin.html",
            _ctx(request, denied=True, message=_t("admin_not_admin")),
        )
    if msg_type not in MSG_TYPES:
        return RedirectResponse("/admin", status_code=303)
    form = await request.form()
    subjects = {
        lang: str(form.get(f"subj_{lang}", "")).strip() for lang in ("ro", "ru", "en")
    }
    bodies = {
        lang: str(form.get(f"body_{lang}", "")).strip() for lang in ("ro", "ru", "en")
    }
    set_msg_templates(msg_type, subjects, bodies)
    return RedirectResponse(f"/admin?tab=messages&saved={msg_type}", status_code=303)


# --------------------------------------------------------------------------- #
# Homes
# --------------------------------------------------------------------------- #
@router.get("/homes", response_class=HTMLResponse)
async def homes_page(
    request: Request,
    page: int = 1,
    user_id: int | None = Depends(optional_auth_token),
):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    per_page = 20
    page = max(1, page)
    all_homes = list_homes(user_id)
    total = len(all_homes)
    total_pages = max(1, (total + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages
    start = (page - 1) * per_page
    return templates.TemplateResponse(
        request, "homes.html",
        _ctx(
            request,
            homes=all_homes[start:start + per_page],
            page=page,
            total_pages=total_pages,
            total=total,
        ),
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
    page: int = 1,
    user_id: int | None = Depends(optional_auth_token),
):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    _t = make_translator(get_lang(request.cookies.get("lang")))
    per_page = 20
    page = max(1, page)
    accounts = list_accounts(user_id, home_id=home_id)
    current_home = get_home(user_id, home_id) if home_id else None
    all_invoices = list_invoices(user_id, home_id=home_id)
    total = len(all_invoices)
    total_pages = max(1, (total + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages
    start = (page - 1) * per_page
    invoices = all_invoices[start:start + per_page]
    generated = request.query_params.get("generated", "") == "1"
    try:
        generated_updated = int(request.query_params.get("updated", "0"))
    except (TypeError, ValueError):
        generated_updated = 0
    try:
        generated_errors = int(request.query_params.get("errors", "0"))
    except (TypeError, ValueError):
        generated_errors = 0
    generated_msg = None
    if generated:
        generated_msg = _t(
            "invoices_generated",
        ).replace("{updated}", str(generated_updated)).replace("{errors}", str(generated_errors))
    return templates.TemplateResponse(
        request, "invoices_all.html",
        _ctx(
            request,
            invoices=invoices,
            accounts=accounts,
            homes=list_homes(user_id),
            current_home=current_home,
            page=page,
            total_pages=total_pages,
            total=total,
            generated=generated,
            generated_msg=generated_msg,
        ),
    )


@router.post("/invoices/generate")
async def invoices_generate(
    request: Request, user_id: int | None = Depends(optional_auth_token)
):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    _t = make_translator(get_lang(request.cookies.get("lang")))
    form = await request.form()
    account_id_raw = form.get("account_id", "all")
    try:
        account_id = int(account_id_raw) if str(account_id_raw).isdigit() else None
    except (TypeError, ValueError):
        account_id = None
    result = await generate_invoices_for_user(user_id, account_id=account_id)
    back = str(form.get("back", "/invoices"))
    if not back.startswith("/") or back.startswith("//"):
        back = "/invoices"
    return RedirectResponse(
        f"{back}?generated=1&updated={result['updated_accounts']}&errors={result['errors']}",
        status_code=303,
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
