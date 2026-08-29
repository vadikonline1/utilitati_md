"""Email delivery via SMTP, using settings configured in the /admin dashboard.

Message texts are localized per-user language and can be edited by an admin in
the /admin "message management" section. If a custom template is not configured
for a message type + language, a sensible built-in default is used.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from .settings import get_msg_body, get_msg_subject, get_setting

_LOGGER = logging.getLogger(__name__)

DEFAULT_LANG = "ro"

APP = "Utilitati.MD"


def smtp_configured() -> bool:
    return bool(get_setting("smtp_host")) and bool(get_setting("smtp_from"))


def send_email(
    to: str,
    subject: str,
    body: str,
    *,
    _force_render: bool = False,
) -> bool:
    """Send a plain-text email. Returns True on success, False otherwise."""
    host = get_setting("smtp_host")
    port = get_setting("smtp_port") or "587"
    user = get_setting("smtp_user")
    password = get_setting("smtp_pass")
    sender = get_setting("smtp_from")

    if not host or not sender:
        _LOGGER.warning("SMTP not configured; email not sent to %s", to)
        return False

    try:
        port_int = int(port)
    except (TypeError, ValueError):
        port_int = 587

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(body.rstrip())

    try:
        with smtplib.SMTP(host, port_int, timeout=30) as smtp:
            smtp.ehlo()
            if port_int == 587:
                smtp.starttls()
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)
        return True
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Failed to send email to %s", to)
        return False


# --------------------------------------------------------------------------- #
# Built-in default templates (per message type, per language)
# --------------------------------------------------------------------------- #
_DEFAULTS: dict[str, dict[str, tuple[str, str]]] = {
    "invite": {
        # (subject, body)
        "ro": (
            "Utilitati.MD — Confirma-ti contul",
            "Salut{comma_name},\n\n"
            "A fost creat un cont pentru tine in sistemul Utilitati.MD.\n\n"
            "Pentru a-ti activa contul, confirma adresa de email apasand linkul de mai jos:\n"
            "    {url}\n\n"
            "Linkul este valid 24 de ore.\n\n"
            "NOTA: Daca nu gasesti emailul in inbox, verifica si dosarul Spam/Junk.\n\n"
            "Echipa Utilitati.MD",
        ),
        "ru": (
            "Utilitati.MD — Подтвердите аккаунт",
            "Здравствуйте{comma_name},\n\n"
            "Для вас создан аккаунт в системе Utilitati.MD.\n\n"
            "Чтобы активировать аккаунт, подтвердите адрес email, перейдя по ссылке:\n"
            "    {url}\n\n"
            "Ссылка действительна 24 часа.\n\n"
            "ПРИМЕЧАНИЕ: если вы не видите письмо во входящих, проверьте Спам/Нежелательные.\n\n"
            "Команда Utilitati.MD",
        ),
        "en": (
            "Utilitati.MD — Confirm your account",
            "Hello{comma_name},\n\n"
            "An account has been created for you in the Utilitati.MD system.\n\n"
            "To activate your account, confirm your email address by clicking the link below:\n"
            "    {url}\n\n"
            "The link is valid for 24 hours.\n\n"
            "NOTE: If you don't see the email in your inbox, check your Spam/Junk folder.\n\n"
            "The Utilitati.MD team",
        ),
    },
    "welcome": {
        "ro": (
            "Utilitati.MD — Contul tau a fost activat",
            "Salut{comma_name},\n\n"
            "Adresa ta de email a fost confirmata cu succes. Contul tau este acum activ.\n\n"
            "Te poti autentifica cu datele de mai jos:\n"
            "    Utilizator: {username}\n"
            "    Parola:     {password}\n\n"
            "Recomandam sa-ti schimbi parola dupa prima autentificare, din sectiunea Cont.\n\n"
            "Echipa Utilitati.MD",
        ),
        "ru": (
            "Utilitati.MD — Ваш аккаунт активирован",
            "Здравствуйте{comma_name},\n\n"
            "Ваш email успешно подтверждён. Аккаунт теперь активен.\n\n"
            "Вы можете войти с данными ниже:\n"
            "    Пользователь: {username}\n"
            "    Пароль:       {password}\n\n"
            "Рекомендуем сменить пароль после первого входа (раздел Аккаунт).\n\n"
            "Команда Utilitati.MD",
        ),
        "en": (
            "Utilitati.MD — Your account is active",
            "Hello{comma_name},\n\n"
            "Your email address has been confirmed successfully and your account is now active.\n\n"
            "You can sign in with the following details:\n"
            "    Username: {username}\n"
            "    Password: {password}\n\n"
            "We recommend changing your password after your first login, from the Account section.\n\n"
            "The Utilitati.MD team",
        ),
    },
    "reset": {
        "ro": (
            "Utilitati.MD — Resetarea parolei",
            "Salut{comma_name},\n\n"
            "Am primit o cerere de resetare a parolei pentru contul tau.\n\n"
            "Daca NU ai cerut tu aceasta schimbare, poti ignora acest email — parola ta "
            "nu se va modifica.\n\n"
            "Daca ai cerut resetarea, apasa linkul de mai jos pentru a-ti seta o parola noua:\n"
            "    {url}\n\n"
            "Linkul este valid 1 ora.\n\n"
            "Echipa Utilitati.MD",
        ),
        "ru": (
            "Utilitati.MD — Сброс пароля",
            "Здравствуйте{comma_name},\n\n"
            "Мы получили запрос на сброс пароля для вашего аккаунта.\n\n"
            "Если вы НЕ запрашивали это изменение, можете проигнорировать письмо — пароль "
            "не изменится.\n\n"
            "Если вы запрашивали сброс, перейдите по ссылке, чтобы задать новый пароль:\n"
            "    {url}\n\n"
            "Ссылка действительна 1 час.\n\n"
            "Команда Utilitati.MD",
        ),
        "en": (
            "Utilitati.MD — Password reset",
            "Hello{comma_name},\n\n"
            "We received a request to reset the password for your account.\n\n"
            "If you did NOT request this change, you can ignore this email — your password "
            "will not change.\n\n"
            "If you requested the reset, click the link below to set a new password:\n"
            "    {url}\n\n"
            "The link is valid for 1 hour.\n\n"
            "The Utilitati.MD team",
        ),
    },
    "inactive": {
        "ro": (
            "Utilitati.MD — Contul tau va fi sters",
            "Salut{comma_name},\n\n"
            "Nu ai mai accesat contul tau de mult timp.\n\n"
            "Daca nu te autentifici in urmatoarele {days} de zile, contul tau si datele "
            "asociate vor fi sterse definitiv pe data de {date}.\n\n"
            "Daca vrei sa pastrezi contul, autentifica-te inainte de aceasta data:\n"
            "    {url}\n\n"
            "Echipa Utilitati.MD",
        ),
        "ru": (
            "Utilitati.MD — Ваш аккаунт будет удалён",
            "Здравствуйте{comma_name},\n\n"
            "Вы давно не заходили в свой аккаунт.\n\n"
            "Если вы не войдёте в течение {days} дней, ваш аккаунт и связанные данные будут "
            "окончательно удалены {date}.\n\n"
            "Чтобы сохранить аккаунт, войдите до этой даты:\n"
            "    {url}\n\n"
            "Команда Utilitati.MD",
        ),
        "en": (
            "Utilitati.MD — Your account will be deleted",
            "Hello{comma_name},\n\n"
            "You haven't signed in to your account for a long time.\n\n"
            "If you don't sign in within the next {days} days, your account and associated "
            "data will be permanently deleted on {date}.\n\n"
            "If you want to keep your account, please sign in before that date:\n"
            "    {url}\n\n"
            "The Utilitati.MD team",
        ),
    },
}


def get_default_msg(msg_type: str, lang: str) -> tuple[str, str]:
    """Return the built-in default (subject, body) for a type+lang (admin editor)."""
    try:
        return _DEFAULTS[msg_type][lang]
    except KeyError:
        return _DEFAULTS.get(msg_type, {}).get("ro", ("", ""))


def _resolve(msg_type: str, lang: str) -> tuple[str, str]:
    """Return (subject, body) for a type+lang, preferring admin-custom templates."""
    return (
        get_msg_subject(msg_type, lang)
        or _DEFAULTS[msg_type][lang][0],
        get_msg_body(msg_type, lang)
        or _DEFAULTS[msg_type][lang][1],
    )


def _render(msg_type: str, lang: str, **kwargs) -> tuple[str, str]:
    """Render and return (subject, body) with {placeholders} substituted."""
    subj, body = _resolve(msg_type, lang or DEFAULT_LANG)
    name = kwargs.get("name", "")
    kwargs = dict(kwargs)
    kwargs["comma_name"] = f", {name}" if name else ""
    kwargs.setdefault("name", name)
    try:
        subj = subj.format(**{k: str(v) for k, v in kwargs.items()})
        body = body.format(**{k: str(v) for k, v in kwargs.items()})
    except (KeyError, IndexError):  # pragma: no cover - bad template
        pass
    return subj, body


# --------------------------------------------------------------------------- #
# Public senders (locale-aware)
# --------------------------------------------------------------------------- #
def send_invitation(to: str, user_name: str, confirm_url: str, lang: str = "ro") -> bool:
    subj, body = _render("invite", lang, name=user_name, url=confirm_url)
    return send_email(to, subj, body)


def send_welcome(
    to: str, user_name: str, username: str, password: str, lang: str = "ro"
) -> bool:
    subj, body = _render(
        "welcome", lang, name=user_name, username=username, password=password
    )
    return send_email(to, subj, body)


def send_reset_link(
    to: str, user_name: str, reset_url: str, lang: str = "ro"
) -> bool:
    subj, body = _render("reset", lang, name=user_name, url=reset_url)
    return send_email(to, subj, body)


def send_inactivity_warning(
    to: str,
    user_name: str,
    days: int,
    delete_date: str,
    site_url: str,
    lang: str = "ro",
) -> bool:
    subj, body = _render(
        "inactive", lang, name=user_name, days=days, date=delete_date, url=site_url
    )
    return send_email(to, subj, body)


# --------------------------------------------------------------------------- #
# Legacy aliases kept for backwards compatibility with old call sites.
# --------------------------------------------------------------------------- #
def _invitation_body(user_name: str, confirm_url: str) -> str:
    return _render("invite", "ro", name=user_name, url=confirm_url)[1]


def _welcome_body(user_name: str, username: str, password: str) -> str:
    return _render(
        "welcome", "ro", name=user_name, username=username, password=password
    )[1]


def _reset_body(user_name: str, reset_url: str) -> str:
    return _render("reset", "ro", name=user_name, url=reset_url)[1]
