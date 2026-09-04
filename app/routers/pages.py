"""Page routes (HTML rendering): landing, auth, dashboard, homes, invoices."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.templating import Jinja2Templates

from ..auth import (
    authenticate,
    cancel_deactivation,
    change_password,
    confirm_invitation,
    create_invitation,
    create_session_token,
    deactivate_user,
    get_user,
    get_user_lang,
    is_usable_user,
    list_users,
    new_invitation_token,
    parse_session_token,
    register,
    resolve_reset_token,
    set_notifications_enabled,
    set_password_for_user,
    set_reset_token,
    set_user_active,
    set_user_full_name,
    set_user_lang,
    user_by_email,
    user_state,
    verify_password,
)
from ..config import SECRET_KEY, is_admin_username, SITE_URL, TEMPLATES_DIR
from ..deps import optional_auth_token
from ..i18n import LANG_NAMES, LANGS, get_lang, make_translator
from ..services import contact as contact_svc
from ..services import email as email_svc
from ..services import faq as faq_svc
from ..services import notify as notify_svc
from ..services import pages as pages_svc
from ..services import push as push_svc
from ..services import telegram as telegram_svc
from ..services.settings import (
    MSG_TYPES,
    MASKED,
    admob_config,
    all_settings,
    clear_msg_templates,
    delete_setting,
    get_setting,
    get_sync_interval_hours,
    inactive_months,
    invoice_months,
    msg_templates,
    retention_enabled,
    set_msg_templates,
    set_setting,
    set_settings,
    settings_with_prefix,
    unconfirmed_hours,
    warn_days,
)
from ..services.sync import dashboard_stats, enqueue_invoice_job, job_info
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
    "cet_nord": {"icon": "🔥", "name": "CET Nord", "fields": ["contract"], "account_label": "Numărul facturii", "placeholder": "1-9 cifre (ex: 123456789)"},
    "paza_a_mai": {"icon": "🔒", "name": "Paza a MAI", "fields": ["contract"], "account_label": "Factura", "placeholder": "1-20 caractere (ex: 12345)"},
    "probon": {"icon": "📋", "name": "Probon", "fields": ["contract"], "account_label": "ID Client", "placeholder": "1-10 caractere (ex: 1234567890)"},
    "eco_mereni": {"icon": "🌿", "name": "Eco-Mereni", "fields": ["contract"], "account_label": "Cod LUC", "placeholder": "4 cifre (ex: 1234)"},
    "antar_salubrizare": {"icon": "🗑️", "name": "ANTAR SALUBRIZARE", "fields": ["contract"], "account_label": "Numarul contractului", "placeholder": "7-9 cifre (ex: 1234567)"},
    "anintercom": {"icon": "🏢", "name": "Anintercom", "fields": ["contract"], "account_label": "Numar contract", "placeholder": "7 cifre (ex: 1234567)"},
    "sagaidac_service": {"icon": "🏠", "name": "Sagaidac Service", "fields": ["contract"], "account_label": "Numarul contractului", "placeholder": "7-9 cifre (ex: 1234567)"},
    "vipinterfon": {"icon": "🚪", "name": "VIP Interfon", "fields": ["contract"], "account_label": "Numar contract", "placeholder": "4-5 cifre (ex: 1234)"},
    "econdominiu": {"icon": "🏢", "name": "E-Condominiu", "fields": ["contract"], "account_label": "Cod Consumator", "placeholder": "max 11 caractere (ex: 12345678901)"},
    "salubeco": {"icon": "🗑️", "name": "SALUBECO", "fields": ["contract"], "account_label": "Numarul contractului", "placeholder": "max 9 cifre (ex: 123456789)"},
    "legion_security_group": {"icon": "🛡️", "name": "LEGION SECURITY GROUP", "fields": ["contract"], "account_label": "Personal ID", "placeholder": "max 5 caractere (ex: 12345)"},
    "invoicer": {"icon": "🧾", "name": "Invoicer", "fields": ["contract"], "account_label": "ID platitor", "placeholder": "max 14 caractere (ex: 12345678901234)"},
}


def _ctx(request, **extra):
    uid = parse_session_token(request.cookies.get("session") or "")
    # Per-user platform language takes priority over the browser/cookie choice.
    lang = get_user_lang(uid) if uid is not None else None
    if lang is None:
        lang = get_lang(request.cookies.get("lang"))
    user_full_name = ""
    if uid is not None:
        _user = get_user(uid)
        if _user:
            user_full_name = _user.get("full_name") or ""
    ctx = {
        "request": request,
        "now": datetime.now(),
        "SITE_URL": SITE_URL,
        "providers": PROVIDER_META,
        "lang": lang,
        "t": make_translator(lang),
        "langs": LANG_NAMES,
        "logged_in": uid is not None and is_usable_user(uid),
        "user_full_name": user_full_name,
        "is_admin": uid is not None and is_usable_user(uid)
        and is_admin_username(get_username(uid)),
        "seo": _seo(),
    }
    ctx.update(extra)
    return ctx


def _job_wait_response(request: Request, url: str, attempt: int, message: str):
    """Render the 'verificăm... așteptați' page while a background job runs.

    The page auto-reloads ``url`` every few seconds via a meta refresh; when the
    worker has finished the job the handler renders the normal result instead.
    ``attempt`` caps the reloads so an error never leaves the user stuck.
    """
    return templates.TemplateResponse(
        request,
        "invoice_job_wait.html",
        _ctx(
            request,
            next_url=url,
            attempt=attempt,
            message=message,
            max_attempts=60,
        ),
    )


# --------------------------------------------------------------------------- #
# SEO / company info exposed to every template (metas + custom head/footer HTML)
# --------------------------------------------------------------------------- #
def _seo() -> dict:
    """Site-wide SEO values from /admin?tab=seo, included in every page context."""
    return {
        "meta_title": get_setting("meta_default_title", "").strip(),
        "meta_description": get_setting("meta_default_description", "").strip(),
        "meta_keywords": get_setting("meta_default_keywords", "").strip(),
        "google_verification": get_setting("google_verification", "").strip(),
        "search_verification_html": get_setting("search_verification_html", ""),
        "header_html": get_setting("header_html", ""),
        "footer_html": get_setting("footer_html", ""),
        "company_name": get_setting("company_name", "").strip() or "UTILITĂȚI.MD",
        "company_email": get_setting("company_email", "").strip(),
        "company_address": get_setting("company_address", "").strip(),
    }


BUILTIN_PLACEHOLDERS = (
    "company_name", "company_email", "company_address", "site", "contact", "privacy",
)


def _page_tokens_defaults() -> dict:
    """Default {placeholder: value} pairs (company info + site addresses)."""
    seo = _seo()
    return {
        "company_name": seo["company_name"] or "UTILITĂȚI.MD",
        "company_email": seo["company_email"] or f"{SITE_URL}/contact",
        "company_address": seo["company_address"] or "—",
        "site": SITE_URL,
        "contact": f"{SITE_URL}/contact",
        "privacy": f"{SITE_URL}/privacy",
    }


def _page_tokens() -> dict:
    """Live placeholder values for {company_name} etc. inside page content.

    Stored overrides (`placeholder_<name>` settings, editable in the SEO tab)
    take precedence over the computed defaults so admins can replace any value
    or add brand-new placeholders for their own page content.
    """
    tokens = _page_tokens_defaults()
    for name, value in settings_with_prefix("placeholder_").items():
        if value:
            tokens[name] = value
    return tokens


def _page_placeholder_rows() -> list[dict]:
    """Current placeholder state for the SEO tab editor (builtin + custom)."""
    defaults = _page_tokens_defaults()
    overrides = settings_with_prefix("placeholder_")
    rows = [
        {"name": name, "value": defaults.get(name, ""), "is_builtin": True,
         "is_override": name in overrides and bool(overrides[name])}
        for name in BUILTIN_PLACEHOLDERS
    ]
    for name in sorted(overrides):
        if name not in BUILTIN_PLACEHOLDERS and overrides[name]:
            rows.append({"name": name, "value": overrides[name],
                         "is_builtin": False, "is_override": True})
    return rows


# --------------------------------------------------------------------------- #
# Anti-spam math captcha (stateless: operands + answer inside a signed token)
# --------------------------------------------------------------------------- #
def _new_captcha() -> dict[str, str]:
    """Return {question, token} for a simple 'a + b = ?' challenge.

    The token is an HMAC signature over the base64-encoded operands, so the
    server can verify the submitted answer without any server-side state or
    session cookie.
    """
    a = secrets.randbelow(8) + 2
    b = secrets.randbelow(8) + 2
    payload = base64.urlsafe_b64encode(f"{a}+{b}".encode()).decode()
    sig = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return {
        "question": f"{a} + {b} = ?",
        "token": f"{payload}.{sig}",
    }


def _check_captcha(token: str, answer: str) -> bool:
    """Validate a captcha submission: token well-formed + answer correct."""
    try:
        payload, sig = token.rsplit(".", 1)
        if not hmac.compare_digest(
            sig,
            hmac.new(
                SECRET_KEY.encode(), payload.encode(), hashlib.sha256
            ).hexdigest(),
        ):
            return False
        a_s, b_s = base64.urlsafe_b64decode(payload.encode()).decode().split("+")
        return int(answer.strip()) == int(a_s) + int(b_s)
    except (ValueError, TypeError, AttributeError):
        return False


# --------------------------------------------------------------------------- #
# Public landing page
# --------------------------------------------------------------------------- #
@router.get("/", response_class=HTMLResponse)
async def home(request: Request, user_id: int | None = Depends(optional_auth_token)):
    return templates.TemplateResponse(
        request, "home.html",
        _ctx(
            request,
            logged_in=user_id is not None,
            faq_items=faq_svc.list_faq_items(),
            providers=PROVIDER_META,
        ),
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
# Public content pages (privacy / about / custom) sourced from the pages table,
# editable by admins in /admin?tab=pages.
# --------------------------------------------------------------------------- #
def _page_ctx(request: Request, page: dict, lang: str, **extra) -> dict:
    """Context for rendering a content page (title, html body, SEO meta)."""
    title = (page.get(f"title_{lang}") or page.get("title_ro") or "").strip()
    body = (page.get(f"content_{lang}") or page.get("content_ro") or "").strip()
    meta_title = (page.get("meta_title") or "").strip() or title
    meta_description = (page.get("meta_description") or "").strip()
    return _ctx(
        request,
        page=page,
        page_title=title,
        page_body=pages_svc.render_content(body, _page_tokens()),
        page_meta_title=meta_title,
        page_meta_description=meta_description,
        page_url=f"{SITE_URL}/{page['slug']}",
        **extra,
    )


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request, user_id: int | None = Depends(optional_auth_token)):
    page = pages_svc.get_page("privacy")
    if page is None:
        return templates.TemplateResponse(
            request, "privacy.html",
            _ctx(request, logged_in=user_id is not None),
        )
    lang = get_user_lang(user_id) or get_lang(request.cookies.get("lang"))
    return templates.TemplateResponse(
        request, "page.html", _page_ctx(request, page, lang)
    )


@router.get("/about", response_class=HTMLResponse)
async def about_page(request: Request, user_id: int | None = Depends(optional_auth_token)):
    page = pages_svc.get_page("about")
    if page is None:
        return RedirectResponse("/", status_code=303)
    lang = get_user_lang(user_id) or get_lang(request.cookies.get("lang"))
    return templates.TemplateResponse(
        request, "page.html", _page_ctx(request, page, lang)
    )


@router.get("/page/{slug}", response_class=HTMLResponse)
async def content_page(
    slug: str, request: Request, user_id: int | None = Depends(optional_auth_token)
):
    page = pages_svc.get_page(slug)
    if page is None:
        return templates.TemplateResponse(
            request, "page.html",
            _ctx(request, page=None, page_title="404", page_body="",
                 page_meta_title="404", page_meta_description="", page_url=""),
            status_code=404,
        )
    lang = get_user_lang(user_id) or get_lang(request.cookies.get("lang"))
    return templates.TemplateResponse(
        request, "page.html", _page_ctx(request, page, lang)
    )


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    return PlainTextResponse(
        f"User-agent: *\n"
        f"Allow: /\n"
        f"Sitemap: {SITE_URL}/sitemap.xml\n"
    )


@router.get("/sitemap.xml", response_class=Response)
async def sitemap_xml():
    now = datetime.now().strftime("%Y-%m-%d")
    urls = [("/", now), ("/about", now), ("/privacy", now), ("/contact", now),
            ("/login", now), ("/register", now)]
    for page in pages_svc.list_pages():
        path = f"/page/{page['slug']}"
        if page["slug"] == "about":
            path = "/about"
        elif page["slug"] == "privacy":
            path = "/privacy"
        elif page["slug"] == "contact":
            path = "/contact"
        urls.append((path, (page.get("updated_at") or now)[:10]))
    locs = "".join(
        f"  <url><loc>{SITE_URL}{path}</loc><lastmod>{lastmod}</lastmod></url>\n"
        for path, lastmod in urls
    )
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{locs}"
        "</urlset>\n"
    )
    return Response(content=xml_text, media_type="application/xml")


@router.get("/contact", response_class=HTMLResponse)
async def contact_page(request: Request, user_id: int | None = Depends(optional_auth_token)):
    return templates.TemplateResponse(
        request, "contact.html",
        _contact_page_ctx(request, captcha=_new_captcha(), error=None, done=None),
    )


@router.post("/contact")
async def contact_submit(request: Request):
    _t = make_translator(get_lang(request.cookies.get("lang")))
    form = await request.form()
    name = str(form.get("name", "")).strip()
    email = str(form.get("email", "")).strip()
    subject = str(form.get("subject", "")).strip()
    message = str(form.get("message", "")).strip()
    token = str(form.get("captcha_token", ""))
    answer = str(form.get("captcha_answer", ""))

    if not _check_captcha(token, answer):
        return templates.TemplateResponse(
            request, "contact.html",
            _contact_page_ctx(request, captcha=_new_captcha(), error=_t("contact_captcha_bad"), done=None),
            status_code=400,
        )
    if not name or not email or not message:
        return templates.TemplateResponse(
            request, "contact.html",
            _contact_page_ctx(request, captcha=_new_captcha(), error=_t("contact_fill_all"), done=None),
            status_code=400,
        )
    if "@" not in email or "." not in email.split("@")[-1]:
        return templates.TemplateResponse(
            request, "contact.html",
            _contact_page_ctx(request, captcha=_new_captcha(), error=_t("contact_email_bad"), done=None),
            status_code=400,
        )

    contact_svc.save_contact_message(name, email, subject, message)

    # Notify the admin (smtp_from is the site's own mailbox) when SMTP is set up.
    if email_svc.smtp_configured():
        try:
            email_svc.send_email(
                get_setting("smtp_from"),
                f"Contact{(' — ' + subject) if subject else ''}: {name}",
                f"De la: {name} <{email}>\n"
                f"Subiect: {subject}\n\n{message}",
            )
        except Exception:  # noqa: BLE001 - notification must never break the form
            pass

    return templates.TemplateResponse(
        request, "contact.html",
        _contact_page_ctx(
            request,
            captcha=_new_captcha(),
            error=None,
            done=_t("contact_done"),
        ),
    )


def _contact_page_ctx(request: Request, **extra) -> dict:
    """Contact page context: editable intro (from the pages table) + the form."""
    base = _ctx(request)
    page = pages_svc.get_page("contact")
    if page is None:
        return dict(base, page_title="", page_body="", **extra)
    lang = base["lang"]
    return dict(
        base,
        page=page,
        page_title=(page.get(f"title_{lang}") or page.get("title_ro") or "").strip(),
        page_body=pages_svc.render_content(
            (page.get(f"content_{lang}") or page.get("content_ro") or "").strip(),
            _page_tokens(),
        ),
        **extra,
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
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", "")).strip()
    user_id = authenticate(username, password)
    if user_id is None:
        _t = make_translator(get_lang(request.cookies.get("lang")))
        state = user_state(username)
        if state is not None and state["deactivated"]:
            message = _t("login_deactivated")
        else:
            message = _t("login_invalid")
        return templates.TemplateResponse(
            request, "login.html", _ctx(request, error=message),
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
        lang = get_user_lang(user["id"]) or get_lang(request.cookies.get("lang"))
        email_svc.send_reset_link(
            email, user.get("full_name", ""), reset_url, lang=lang,
        )
        # If the user has chat id(s) saved, also deliver the reset link via Telegram.
        full = get_user(user["id"]) or {}
        chat_ids = full.get("telegram_chat_ids", "")
        if chat_ids:
            await telegram_svc.send_reset_link_to_chats(chat_ids, reset_url, lang)
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
    new_password = str(form.get("password", "")).strip()
    confirm = str(form.get("confirm", "")).strip()
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


def _profile_ctx(request: Request, user_id: int, message: str | None = None, **extra) -> dict:
    """Profile page context: identity, language, notification prefs and admin flag."""
    prefs = get_notification_prefs(user_id)
    lang = get_user_lang(user_id) or get_lang(request.cookies.get("lang"))
    user = get_user(user_id) or {}
    return _ctx(
        request,
        message=message,
        username=get_username(user_id),
        user_lang=lang,
        user_full_name=user.get("full_name") or "",
        user_email=user.get("email") or "",
        emails=prefs["emails"],
        telegram_chat_ids=prefs["telegram"],
        email_configured=_email_cfg(),
        telegram_configured=_telegram_cfg(),
        telegram_bot_url=_telegram_bot_url(),
        is_admin=_is_admin(user_id),
        **extra,
    )


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, user_id: int | None = Depends(optional_auth_token)):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request, "profile.html", _profile_ctx(request, user_id),
    )


@router.get("/notifications", response_class=HTMLResponse)
async def notifications_page(request: Request, user_id: int | None = Depends(optional_auth_token)):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    ctx = _ctx(request, notifications=push_svc.list_user_notifications(user_id))
    return templates.TemplateResponse(request, "notifications.html", ctx)


@router.post("/profile")
async def profile_submit(request: Request, user_id: int | None = Depends(optional_auth_token)):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    _t = make_translator(get_user_lang(user_id) or get_lang(request.cookies.get("lang")))
    form = await request.form()
    if form.get("first_name") is not None or form.get("last_name") is not None:
        first_name = str(form.get("first_name", "")).strip()
        last_name = str(form.get("last_name", "")).strip()
        full_name = f"{first_name} {last_name}".strip()
        set_user_full_name(user_id, full_name)
        return templates.TemplateResponse(
            request, "profile.html",
            _profile_ctx(request, user_id, message=_t("profile_name_saved")),
        )
    old = str(form.get("old_password", "")).strip()
    new = str(form.get("new_password", "")).strip()
    confirm = str(form.get("confirm", "")).strip()
    if new != confirm:
        return templates.TemplateResponse(
            request, "profile.html", _profile_ctx(request, user_id, message=_t("profile_mismatch")),
        )
    if change_password(user_id, old, new):
        return templates.TemplateResponse(
            request, "profile.html", _profile_ctx(request, user_id, message=_t("profile_changed")),
        )
    return templates.TemplateResponse(
        request, "profile.html", _profile_ctx(request, user_id, message=_t("profile_wrong_old")),
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
        str(form.get("emails", "")).strip(),
        str(form.get("telegram_chat_ids", "")).strip(),
    )
    return templates.TemplateResponse(
        request, "profile.html",
        _profile_ctx(request, user_id, message=_t("profile_notif_saved")),
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


@router.post("/profile/deactivate")
async def profile_deactivate_submit(
    request: Request, user_id: int | None = Depends(optional_auth_token)
):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    _t = make_translator(get_user_lang(user_id) or get_lang(request.cookies.get("lang")))
    form = await request.form()
    password = str(form.get("password", "")).strip()
    if not verify_password(user_id, password):
        return templates.TemplateResponse(
            request, "profile.html",
            _profile_ctx(request, user_id, message=_t("profile_deactivate_wrong_password")),
        )
    delete_after = deactivate_user(user_id)
    # Log the user out: their session is no longer usable.
    display_date = delete_after
    try:
        display_date = datetime.fromisoformat(delete_after).strftime("%d.%m.%Y")
    except ValueError:
        pass
    response = templates.TemplateResponse(
        request, "deactivated.html",
        _ctx(
            request,
            logged_in=False,
            delete_after=display_date,
            message=_t("profile_deactivated"),
        ),
    )
    response.delete_cookie("session")
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


def _msg_defaults_data() -> dict:
    """{msg_type: {lang: {subj, body}}} with the built-in default templates."""
    return {
        mt: {
            lang: {"subj": email_svc.get_default_msg(mt, lang)[0],
                   "body": email_svc.get_default_msg(mt, lang)[1]}
            for lang in ("ro", "ru", "en")
        }
        for mt in MSG_TYPES
    }


def _admin_base_ctx() -> dict:
    """Context values shared by every /admin render."""
    return {
        "denied": False,
        "settings": all_settings(),
        "admob": admob_config(),
        "fcm_configured": bool(
            get_setting("fcm_service_account", "").strip()
            or os.getenv("FCM_SERVICE_ACCOUNT", "").strip()
        ),
        "default_push_title": "Notificare administrativă - UTILITĂȚI.MD",
        "retention_enabled": retention_enabled(),
        "inactive_months": inactive_months(),
        "warn_days_list": warn_days(),
        "invoice_months": invoice_months(),
        "unconfirmed_hours": unconfirmed_hours(),
        "msg_types": MSG_TYPES,
        "msg_templates_data": {mt: msg_templates(mt) for mt in MSG_TYPES},
        "msg_defaults_data": _msg_defaults_data(),
        "contact_messages": contact_svc.list_contact_messages(),
        "users": list_users(),
        "faq_items": faq_svc.list_faq_items(),
        "pages": pages_svc.list_pages(),
        "page_placeholders": pages_svc.PLACEHOLDERS,
        "placeholder_rows": _page_placeholder_rows(),
        "current_uid": None,
    }


def _admin_render(request: Request, user_id: int | None, message: str | None = None, **extra) -> HTMLResponse:
    """Render the admin page with the shared context plus any per-route extras."""
    ctx = _admin_base_ctx()
    ctx["current_uid"] = user_id
    if message is not None:
        ctx["message"] = message
    ctx.update(extra)
    return templates.TemplateResponse(request, "admin.html", _ctx(request, **ctx))


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, user_id: int | None = Depends(optional_auth_token)):
    _t = make_translator(get_lang(request.cookies.get("lang")))
    if not _is_admin(user_id):
        return templates.TemplateResponse(
            request, "admin.html",
            _ctx(request, denied=True, message=_t("admin_not_admin")),
        )
    return _admin_render(request, user_id)


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
        "smtp_host": str(form.get("smtp_host", "")).strip(),
        "smtp_port": str(form.get("smtp_port", "")).strip(),
        "smtp_user": str(form.get("smtp_user", "")).strip(),
        "smtp_pass": str(form.get("smtp_pass", "")).strip(),
        "smtp_from": str(form.get("smtp_from", "")).strip(),
        "telegram_token": str(form.get("telegram_token", "")).strip(),
        "telegram_botname": str(form.get("telegram_botname", "")).strip(),
        "sync_mode": sync_mode,
        "retention_enabled": "1" if form.get("retention_enabled") else "0",
        "inactive_months": str(form.get("inactive_months", "12")).strip(),
        "warn_days": str(form.get("warn_days", "90,60,30")).strip(),
        "invoice_months": str(form.get("invoice_months", "24")).strip(),
        "unconfirmed_hours": str(form.get("unconfirmed_hours", "1")).strip(),
        "fcm_service_account": str(form.get("fcm_service_account", "")).strip(),
        "push_provider": str(form.get("push_provider", "fcm")).strip(),
    }
    if sync_mode == "interval":
        try:
            values["sync_hours"] = str(max(1, min(168, int(float(sync_hours)))))
        except (TypeError, ValueError):
            values["sync_hours"] = "24"
    # Secret fields show a masked sentinel instead of the real value; a masked or
    # empty submission means "leave it unchanged" so we never write the sentinel
    # back or wipe a configured credential by accident.
    for secret_key in ("smtp_user", "smtp_pass", "telegram_token", "fcm_service_account"):
        sub = str(values.get(secret_key, "")).strip()
        if not sub or sub == MASKED:
            values.pop(secret_key, None)
    set_settings(values)
    # FCM credentials may have changed -> drop cached token/service account.
    if "fcm_service_account" in values:
        push_svc.clear_fcm_cache()
    return _admin_render(request, user_id, message=_t("admin_saved"))


@router.post("/admin/telegram/set-webhook")
async def admin_telegram_set_webhook(
    request: Request, user_id: int | None = Depends(optional_auth_token)
):
    _t = make_translator(get_lang(request.cookies.get("lang")))
    if not _is_admin(user_id):
        return templates.TemplateResponse(
            request, "admin.html",
            _ctx(request, denied=True, message=_t("admin_not_admin")),
        )
    webhook_url = f"{SITE_URL}/telegram/webhook"
    ok, detail = await telegram_svc.set_webhook(webhook_url)
    if ok:
        message = _t("admin_telegram_webhook_ok") + f" · {webhook_url}"
    else:
        message = _t("admin_telegram_webhook_err") + (f" · {detail}" if detail else "")
    return _admin_render(request, user_id, message=message)


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """Public Telegram webhook: greet on /start and expose the chat id on command."""
    try:
        data = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False}, status_code=400)
    update = data if isinstance(data, dict) else {}
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    frm = message.get("from") or {}
    chat_id = chat.get("id")
    text = str(message.get("text", "")).strip()
    first_name = frm.get("first_name") or ""
    lang_code = frm.get("language_code") or ""
    command = text.split()[0] if text else ""
    if chat_id is not None and (command.startswith("/start") or command.startswith("/chat_id")):
        reply = _tg_command_reply(command, chat_id, first_name, lang_code)
        await telegram_svc.send_message(chat_id, reply)
    return JSONResponse({"ok": True})


_TG_LANGS = {"ro", "ru", "en"}
_DEFAULT_TG_LANG = "ro"

_TG_START = {
    "ro": "Salut{comma_name}! Bun venit la Utilități.MD.\n\n"
          "Chat ID-ul tău: {chat_id}\n\n"
          "Adaugă acest ID în profilul tău, la Notificări, ca să primești "
          "notificări și linkuri de resetare aici.",
    "ru": "Привет{comma_name}! Добро пожаловать в Utilități.MD.\n\n"
          "Ваш chat ID: {chat_id}\n\n"
          "Добавьте этот ID в свой профиль (в раздел Notificări / Уведомления), "
          "чтобы получать уведомления и ссылки для сброса здесь.",
    "en": "Hi{comma_name}! Welcome to Utilități.MD.\n\n"
          "Your chat ID: {chat_id}\n\n"
          "Add this ID to your profile, under Notifications, to receive "
          "notifications and password-reset links here.",
}

_TG_CHAT_ID = {
    "ro": "Chat ID-ul tău: {chat_id}",
    "ru": "Ваш chat ID: {chat_id}",
    "en": "Your chat ID: {chat_id}",
}


def _tg_command_reply(command: str, chat_id, first_name: str, lang_code: str) -> str:
    """Build the bot reply (in the user's Telegram language) for a bot command."""
    lang = lang_code.lower().split("-")[0]
    if lang not in _TG_LANGS:
        lang = _DEFAULT_TG_LANG
    comma_name = f", {first_name}" if first_name else ""
    if command.startswith("/chat_id"):
        return _TG_CHAT_ID[lang].format(chat_id=chat_id)
    return _TG_START[lang].format(chat_id=chat_id, comma_name=comma_name)


# --------------------------------------------------------------------------- #
# New-invoices notification (sent when a provider account connects & finds bills,
# and by the background sync when new invoices appear). Text is admin-editable
# in /admin?tab=messages ("invoices" message type).
# --------------------------------------------------------------------------- #
async def _notify_invoices_found(
    user_id: int, account: dict, fetched, saved_ids: list[int], site_url: str
) -> None:
    """Send the editable 'new invoices' notification (email + Telegram)."""
    if not saved_ids:
        return
    await notify_svc.notify_new_invoices(user_id, account, fetched, saved_ids, site_url)


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


@router.post("/admin/messages/{msg_type}/reset")
async def admin_messages_reset(
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
    clear_msg_templates(msg_type)
    return RedirectResponse(f"/admin?tab=messages&saved={msg_type}", status_code=303)


@router.post("/admin/contact/{message_id}/delete")
async def admin_contact_delete_submit(
    message_id: int, request: Request, user_id: int | None = Depends(optional_auth_token)
):
    _t = make_translator(get_lang(request.cookies.get("lang")))
    if not _is_admin(user_id):
        return templates.TemplateResponse(
            request, "admin.html",
            _ctx(request, denied=True, message=_t("admin_not_admin")),
        )
    contact_svc.delete_contact_message(message_id)
    return RedirectResponse("/admin?tab=contact", status_code=303)


@router.post("/admin/users/{target_id}/status")
async def admin_user_status_submit(
    target_id: int, request: Request, user_id: int | None = Depends(optional_auth_token)
):
    _t = make_translator(get_lang(request.cookies.get("lang")))
    if not _is_admin(user_id):
        return templates.TemplateResponse(
            request, "admin.html",
            _ctx(request, denied=True, message=_t("admin_not_admin")),
        )
    # Never disable yourself (would lock yourself out of the admin panel).
    if target_id != user_id:
        form = await request.form()
        enabled = str(form.get("enabled", "")) == "1"
        set_user_active(target_id, enabled)
    return RedirectResponse("/admin?tab=users", status_code=303)


@router.post("/admin/users/{target_id}/notifications")
async def admin_user_notifications_toggle(
    target_id: int, request: Request, user_id: int | None = Depends(optional_auth_token)
):
    _t = make_translator(get_lang(request.cookies.get("lang")))
    if not _is_admin(user_id):
        return templates.TemplateResponse(
            request, "admin.html",
            _ctx(request, denied=True, message=_t("admin_not_admin")),
        )
    if target_id != user_id:
        form = await request.form()
        enabled = str(form.get("enabled", "")) == "1"
        set_notifications_enabled(target_id, enabled)
        if not enabled:
            push_svc.clear_device_tokens(target_id)
    return RedirectResponse("/admin?tab=users", status_code=303)


@router.post("/admin/users/{target_id}/resend")
async def admin_user_resend_submit(
    target_id: int, request: Request, user_id: int | None = Depends(optional_auth_token)
):
    _t = make_translator(get_lang(request.cookies.get("lang")))
    if not _is_admin(user_id):
        return templates.TemplateResponse(
            request, "admin.html",
            _ctx(request, denied=True, message=_t("admin_not_admin")),
        )
    user = get_user(target_id)
    token = new_invitation_token(target_id) if user else None
    if not user or not token or not user.get("email"):
        return RedirectResponse("/admin?tab=users", status_code=303)
    confirm_url = f"{SITE_URL}/confirm/{token}"
    lang = get_user_lang(target_id) or get_lang(request.cookies.get("lang"))
    sent = email_svc.send_invitation(
        user["email"], user.get("full_name", "") or user.get("username", ""),
        confirm_url, lang=lang,
    )
    chat_ids = user.get("telegram_chat_ids", "")
    if chat_ids:
        await telegram_svc.send_invitation_to_chats(chat_ids, confirm_url, lang)
    return RedirectResponse(
        f"/admin?tab=users&resend={1 if sent or chat_ids else 0}&u={target_id}",
        status_code=303,
    )


# --------------------------------------------------------------------------- #
# FAQ management (admin)
# --------------------------------------------------------------------------- #
def _faq_from_form(form, faq_id: int | None = None) -> dict[str, str]:
    return {
        "question_ro": str(form.get("question_ro", "")).strip(),
        "question_ru": str(form.get("question_ru", "")).strip(),
        "question_en": str(form.get("question_en", "")).strip(),
        "answer_ro": str(form.get("answer_ro", "")).strip(),
        "answer_ru": str(form.get("answer_ru", "")).strip(),
        "answer_en": str(form.get("answer_en", "")).strip(),
    }


@router.post("/admin/faq")
async def admin_faq_add_submit(
    request: Request, user_id: int | None = Depends(optional_auth_token)
):
    _t = make_translator(get_lang(request.cookies.get("lang")))
    if not _is_admin(user_id):
        return templates.TemplateResponse(
            request, "admin.html",
            _ctx(request, denied=True, message=_t("admin_not_admin")),
        )
    form = await request.form()
    faq_svc.add_faq_item(_faq_from_form(form))
    return RedirectResponse("/admin?tab=faq", status_code=303)


@router.post("/admin/faq/{faq_id}")
async def admin_faq_edit_submit(
    faq_id: int, request: Request, user_id: int | None = Depends(optional_auth_token)
):
    _t = make_translator(get_lang(request.cookies.get("lang")))
    if not _is_admin(user_id):
        return templates.TemplateResponse(
            request, "admin.html",
            _ctx(request, denied=True, message=_t("admin_not_admin")),
        )
    form = await request.form()
    faq_svc.update_faq_item(faq_id, _faq_from_form(form))
    return RedirectResponse("/admin?tab=faq", status_code=303)


@router.post("/admin/faq/{faq_id}/delete")
async def admin_faq_delete_submit(
    faq_id: int, request: Request, user_id: int | None = Depends(optional_auth_token)
):
    _t = make_translator(get_lang(request.cookies.get("lang")))
    if not _is_admin(user_id):
        return templates.TemplateResponse(
            request, "admin.html",
            _ctx(request, denied=True, message=_t("admin_not_admin")),
        )
    faq_svc.delete_faq_item(faq_id)
    return RedirectResponse("/admin?tab=faq", status_code=303)


# --------------------------------------------------------------------------- #
# SEO / company settings (admin) + custom head/footer HTML injection
# --------------------------------------------------------------------------- #
@router.post("/admin/seo")
async def admin_seo_submit(
    request: Request, user_id: int | None = Depends(optional_auth_token)
):
    _t = make_translator(get_lang(request.cookies.get("lang")))
    if not _is_admin(user_id):
        return templates.TemplateResponse(
            request, "admin.html",
            _ctx(request, denied=True, message=_t("admin_not_admin")),
        )
    form = await request.form()
    set_settings({
        "meta_default_title": str(form.get("meta_default_title", "")).strip(),
        "meta_default_description": str(form.get("meta_default_description", "")).strip(),
        "meta_default_keywords": str(form.get("meta_default_keywords", "")).strip(),
        "google_verification": str(form.get("google_verification", "")).strip(),
        "search_verification_html": str(form.get("search_verification_html", "")),
        "header_html": str(form.get("header_html", "")),
        "footer_html": str(form.get("footer_html", "")),
        "company_name": str(form.get("company_name", "")).strip(),
        "company_email": str(form.get("company_email", "")).strip(),
        "company_address": str(form.get("company_address", "")).strip(),
    })
    _save_placeholder_rows(form)
    return _admin_render(request, user_id, message=_t("admin_saved"))


@router.post("/admin/ads")
async def admin_ads_submit(
    request: Request, user_id: int | None = Depends(optional_auth_token)
):
    """Save AdMob/Google Ads settings (toggles, unit ids, placements)."""
    _t = make_translator(get_lang(request.cookies.get("lang")))
    if not _is_admin(user_id):
        return templates.TemplateResponse(
            request, "admin.html",
            _ctx(request, denied=True, message=_t("admin_not_admin")),
        )
    form = await request.form()
    placements = ",".join(
        p.strip()
        for p in str(form.get("admob_placements", "")).replace("\n", ",").split(",")
        if p.strip()
    )
    set_settings({
        "admob_enabled": "1" if form.get("admob_enabled") else "0",
        "admob_app_id_android": str(form.get("admob_app_id_android", "")).strip(),
        "admob_app_id_ios": str(form.get("admob_app_id_ios", "")).strip(),
        "admob_banner_enabled": "1" if form.get("admob_banner_enabled") else "0",
        "admob_banner_unit_android": str(form.get("admob_banner_unit_android", "")).strip(),
        "admob_banner_unit_ios": str(form.get("admob_banner_unit_ios", "")).strip(),
        "admob_interstitial_enabled": "1" if form.get("admob_interstitial_enabled") else "0",
        "admob_interstitial_unit_android": str(form.get("admob_interstitial_unit_android", "")).strip(),
        "admob_interstitial_unit_ios": str(form.get("admob_interstitial_unit_ios", "")).strip(),
        "admob_interstitial_interval": str(form.get("admob_interstitial_interval", "5")).strip(),
        "admob_rewarded_enabled": "1" if form.get("admob_rewarded_enabled") else "0",
        "admob_rewarded_unit_android": str(form.get("admob_rewarded_unit_android", "")).strip(),
        "admob_rewarded_unit_ios": str(form.get("admob_rewarded_unit_ios", "")).strip(),
        "admob_placements": placements,
    })
    return _admin_render(request, user_id, message=_t("admin_saved"))


@router.post("/admin/push")
async def admin_push_send(
    request: Request, user_id: int | None = Depends(optional_auth_token)
):
    """Send a push notification from the admin panel."""
    _t = make_translator(get_lang(request.cookies.get("lang")))
    if not _is_admin(user_id):
        return JSONResponse({"error": _t("admin_not_admin")}, status_code=403)
    data = await request.json()
    title = str(data.get("title", "")).strip()
    body = str(data.get("body", "")).strip()
    recipient = str(data.get("recipient", "all")).strip()
    if not title or not body:
        return JSONResponse({"error": "Title and body are required."}, status_code=400)
    if recipient == "all":
        users = list_users()
        user_ids = [u["id"] for u in users if u.get("is_active")]
    else:
        try:
            user_ids = [int(recipient)]
        except (TypeError, ValueError):
            return JSONResponse({"error": "Invalid recipient."}, status_code=400)
    result = await push_svc.send_push_multi(user_ids, title, body)
    return JSONResponse(result)


def _save_placeholder_rows(form) -> None:
    """Persist the placeholder editor rows, adding/removing `placeholder_*`
    settings so custom values can be referenced as {name} in page content."""
    names = str(form.get("ph_name", ""))
    if not names:
        return
    names_list = form.getlist("ph_name")
    values_list = form.getlist("ph_value")
    defaults = _page_tokens_defaults()
    previous = set(settings_with_prefix("placeholder_"))
    seen = set()
    valid_key = re.compile(r"^[a-z0-9_]{1,40}$")
    for name_raw, value_raw in zip(names_list, values_list):
        name = str(name_raw or "").strip().lower()
        if not valid_key.match(name):
            continue
        seen.add(name)
        value = str(value_raw or "").strip()
        if not value:
            if name in previous:
                delete_setting(f"placeholder_{name}")
            continue
        if name in BUILTIN_PLACEHOLDERS and value == defaults.get(name, ""):
            if name in previous:
                delete_setting(f"placeholder_{name}")
            continue
        if get_setting(f"placeholder_{name}") != value:
            set_setting(f"placeholder_{name}", value)
    for name in previous:
        if name not in seen:
            delete_setting(f"placeholder_{name}")


# --------------------------------------------------------------------------- #
# Content pages management (admin)
# --------------------------------------------------------------------------- #
def _page_from_form(form, slug_override: str | None = None) -> dict[str, str]:
    slug = (slug_override or str(form.get("slug", ""))).strip().lower()
    return {
        "slug": pages_svc.slugify(slug),
        "title_ro": str(form.get("title_ro", "")).strip(),
        "title_ru": str(form.get("title_ru", "")).strip(),
        "title_en": str(form.get("title_en", "")).strip(),
        "content_ro": str(form.get("content_ro", "")),
        "content_ru": str(form.get("content_ru", "")),
        "content_en": str(form.get("content_en", "")),
        "meta_title": str(form.get("meta_title", "")).strip(),
        "meta_description": str(form.get("meta_description", "")).strip(),
    }


@router.post("/admin/pages")
async def admin_pages_add_submit(
    request: Request, user_id: int | None = Depends(optional_auth_token)
):
    _t = make_translator(get_lang(request.cookies.get("lang")))
    if not _is_admin(user_id):
        return templates.TemplateResponse(
            request, "admin.html",
            _ctx(request, denied=True, message=_t("admin_not_admin")),
        )
    form = await request.form()
    raw_slug = str(form.get("slug", "")).strip().lower()
    data = _page_from_form(form)
    if not raw_slug or not any(
        data.get(f"title_{lg}") for lg in ("ro", "ru", "en")
    ):
        return _admin_render(request, user_id, message=_t("admin_pages_slug_err"))
    if pages_svc.page_exists(data["slug"]):
        return _admin_render(request, user_id, message=_t("admin_pages_exists"))
    pages_svc.add_page(data)
    return RedirectResponse(f"/admin?tab=pages&added={data['slug']}", status_code=303)


@router.post("/admin/pages/{page_id}")
async def admin_pages_edit_submit(
    page_id: int, request: Request, user_id: int | None = Depends(optional_auth_token)
):
    _t = make_translator(get_lang(request.cookies.get("lang")))
    if not _is_admin(user_id):
        return templates.TemplateResponse(
            request, "admin.html",
            _ctx(request, denied=True, message=_t("admin_not_admin")),
        )
    form = await request.form()
    existing = pages_svc.get_page_by_id(page_id)
    if existing is None:
        return RedirectResponse("/admin?tab=pages", status_code=303)
    # Built-in pages keep their fixed slug: the slug input is disabled in the
    # form, so an empty submission must never rename the page.
    if not str(form.get("slug", "")).strip():
        data = _page_from_form(form, slug_override=existing["slug"])
    else:
        data = _page_from_form(form)
    pages_svc.update_page(page_id, data)
    return RedirectResponse(f"/admin?tab=pages", status_code=303)


@router.post("/admin/pages/{page_id}/delete")
async def admin_pages_delete_submit(
    page_id: int, request: Request, user_id: int | None = Depends(optional_auth_token)
):
    _t = make_translator(get_lang(request.cookies.get("lang")))
    if not _is_admin(user_id):
        return templates.TemplateResponse(
            request, "admin.html",
            _ctx(request, denied=True, message=_t("admin_not_admin")),
        )
    pages_svc.delete_page(page_id)
    return RedirectResponse("/admin?tab=pages", status_code=303)


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
        "name": str(form.get("name", "")).strip(),
        "address": str(form.get("address", "")).strip(),
        "floor": str(form.get("floor", "")).strip(),
        "metro_area": str(form.get("metro_area", "")).strip(),
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
        "name": str(form.get("name", "")).strip(),
        "address": str(form.get("address", "")).strip(),
        "floor": str(form.get("floor", "")).strip(),
        "metro_area": str(form.get("metro_area", "")).strip(),
        "status": str(form.get("status", "enabled")).strip(),
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
    provider = str(form.get("provider", "")).strip()
    contract_number = str(form.get("contract_number", "")).strip()
    if not provider or not contract_number:
        return RedirectResponse(f"/homes/{home_id}", status_code=303)

    meta = PROVIDER_META.get(provider, {})
    fields = meta.get("fields", ["contract"])
    _user = get_user(user_id) or {}
    data = {
        "home_id": home_id,
        "provider": provider,
        "label": meta.get("name", provider),
        "contract_number": contract_number,
        "icon": meta.get("icon", "📄"),
        "username": None,
        "password": None,
        "full_name": _user.get("full_name") or None,
        "place_of_consumption": None,
    }
    if "username" in fields:
        data["username"] = str(form.get("username") or "").strip() or None
    if "password" in fields:
        data["password"] = str(form.get("password") or "").strip() or None
    if "full_name" in fields:
        full_name = str(form.get("full_name") or "").strip()
        if not full_name:
            full_name = _user.get("full_name") or ""
        data["full_name"] = full_name or None

    acc_id = upsert_account(user_id, data)
    new_account = get_account_row(user_id, acc_id)
    if new_account is not None:
        fetched = await fetch_account_data(new_account)
        created_ids, _saved_ids = persist_invoices(acc_id, fetched)
        if created_ids:
            await _notify_invoices_found(user_id, new_account, fetched, created_ids, SITE_URL)
    return RedirectResponse(f"/homes/{home_id}?added={acc_id}", status_code=303)


@router.post("/homes/{home_id}/utilities/{account_id}/edit")
async def utility_edit_submit(
    home_id: int, account_id: int, request: Request,
    user_id: int | None = Depends(optional_auth_token),
):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    account = get_account_row(user_id, account_id)
    if account is None or account.get("home_id") != home_id:
        return RedirectResponse(f"/homes/{home_id}", status_code=303)
    form = await request.form()
    provider = str(account.get("provider", "")).strip()
    meta = PROVIDER_META.get(provider, {})
    fields = meta.get("fields", ["contract"])
    contract_number = str(form.get("contract_number", "")).strip()
    if not contract_number:
        return RedirectResponse(f"/homes/{home_id}", status_code=303)
    _user = get_user(user_id) or {}
    data = {
        "home_id": home_id,
        "provider": provider,
        "label": str(form.get("label") or "").strip() or meta.get("name", provider),
        "contract_number": contract_number,
        "icon": meta.get("icon", account.get("icon", "📄")),
        "username": account.get("username"),
        "password": account.get("password"),
        "full_name": account.get("full_name") or _user.get("full_name") or None,
        "place_of_consumption": account.get("place_of_consumption"),
        "status": account.get("status", "enabled"),
    }
    if "username" in fields:
        data["username"] = (str(form.get("username") or "").strip()
                            or account.get("username") or None)
    if "password" in fields:
        data["password"] = (str(form.get("password") or "").strip()
                            or account.get("password") or None)
    if "full_name" in fields:
        data["full_name"] = str(form.get("full_name") or "").strip() or None
    upsert_account(user_id, data, account_id=account_id)
    return RedirectResponse(f"/homes/{home_id}", status_code=303)


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
    account_id: int,
    request: Request,
    job: int | None = None,
    a: int = 1,
    user_id: int | None = Depends(optional_auth_token),
):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    account = get_account_row(user_id, account_id)
    if account is None:
        return RedirectResponse("/dashboard", status_code=303)
    invoices = list_invoices(user_id, account_id)
    if not invoices:
        # No saved data yet: queue a background refresh so the worker fills the
        # page without blocking this request on the provider.
        enqueue_invoice_job(user_id, account_id=account_id)
    # Poll the queued job: keep showing "verificăm..." until it finishes.
    if job is not None and not (job_info(job, user_id) or {}).get("finished"):
        _tw = make_translator(get_lang(request.cookies.get("lang")))
        return _job_wait_response(
            request,
            f"/accounts/{account_id}/invoices?job={job}&a={a + 1}",
            a,
            f"{_tw('invoice_checking')} › {account['label']}",
        )
    history = list_invoice_history(user_id, invoices[0]["id"]) if invoices else []
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
    # Queue the refresh in the background and land on the "verificăm..." page,
    # which auto-reloads and shows the fresh data once the worker finishes.
    job_id = enqueue_invoice_job(user_id, account_id=account_id)
    if job_id:
        return RedirectResponse(f"/accounts/{account_id}/invoices?job={job_id}", status_code=303)
    return RedirectResponse(f"/accounts/{account_id}/invoices", status_code=303)


@router.get("/invoices", response_class=HTMLResponse)
async def invoices_all_page(
    request: Request,
    home_id: int | None = None,
    page: int = 1,
    job: int | None = None,
    a: int = 1,
    user_id: int | None = Depends(optional_auth_token),
):
    if user_id is None:
        return RedirectResponse("/login", status_code=303)
    if job is not None and not (job_info(job, user_id) or {}).get("finished"):
        _tw = make_translator(get_lang(request.cookies.get("lang")))
        return _job_wait_response(
            request,
            f"/invoices?job={job}&a={a + 1}",
            a,
            _tw("invoice_checking_all"),
        )
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
    edit_accounts = {}
    for acc in accounts:
        meta = PROVIDER_META.get(acc["provider"], {})
        edit_accounts[acc["id"]] = {
            "account_id": acc["id"],
            "home_id": acc["home_id"],
            "provider": acc["provider"],
            "provider_name": meta.get("name", acc["provider"]),
            "fields": meta.get("fields", ["contract"]),
            "account_label": meta.get("account_label", ""),
            "label": acc.get("label") or "",
            "contract_number": acc.get("contract_number") or "",
            "username": acc.get("username") or "",
        }
    return templates.TemplateResponse(
        request, "invoices_all.html",
        _ctx(
            request,
            invoices=invoices,
            accounts=accounts,
            homes=list_homes(user_id),
            current_home=current_home,
            edit_accounts=edit_accounts,
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
    job_id = enqueue_invoice_job(user_id, account_id=account_id)
    back = str(form.get("back", "/invoices"))
    if not back.startswith("/") or back.startswith("//"):
        back = "/invoices"
    # Non-blocking: the refresh runs in the background worker. For the generic
    # /invoices page land on the auto-reloading "verificăm..." page that shows
    # the fresh result once the job finishes.
    if account_id is None and job_id and back == "/invoices":
        return RedirectResponse(f"/invoices?job={job_id}", status_code=303)
    return RedirectResponse(f"{back}?generated=1&queued=1", status_code=303)


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
            "amount_mdl": str(form.get("amount_mdl", inv["amount_mdl"] or 0)).strip(),
            "issue_date": str(form.get("issue_date") or "").strip() or None,
            "due_date": str(form.get("due_date") or "").strip() or None,
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
