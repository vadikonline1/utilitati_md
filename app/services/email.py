"""Email delivery via SMTP, using settings configured in the /admin dashboard.

Settings come from the settings table (keys: smtp_host, smtp_port, smtp_user,
smtp_pass, smtp_from). If SMTP is not configured we log the would-be email and
return False so callers can surface a friendly message.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from .settings import get_setting

_LOGGER = logging.getLogger(__name__)


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
# Templated messages
# --------------------------------------------------------------------------- #
def _invitation_body(user_name: str, confirm_url: str) -> str:
    return (
        f"Salut{', ' + user_name if user_name else ''},\n\n"
        "A fost creat un cont pentru tine în sistemul Utilități.MD.\n\n"
        "Pentru a-ți activa contul, confirmă adresa de email apăsând linkul de mai jos:\n"
        f"    {confirm_url}\n\n"
        "Linkul este valid 24 de ore.\n\n"
        "NOTĂ: Dacă nu găsești emailul în inbox, verifică și dosarul Spam/Junk.\n\n"
        "Echipa Utilități.MD"
    )


def _welcome_body(user_name: str, username: str, password: str) -> str:
    return (
        f"Salut{', ' + user_name if user_name else ''},\n\n"
        "Emailul tău a fost confirmat cu succes. Contul tău este acum activ.\n\n"
        "Poți să te autentifici cu datele de mai jos:\n"
        f"    Utilizator: {username}\n"
        f"    Parola:     {password}\n\n"
        "Recomandăm să-ți schimbi parola după prima autentificare, din secțiunea Cont.\n\n"
        "Echipa Utilități.MD"
    )


def _reset_body(user_name: str, reset_url: str) -> str:
    return (
        f"Salut{', ' + user_name if user_name else ''},\n\n"
        "Am primit o cerere de resetare a parolei pentru contul tău.\n\n"
        "Dacă NU ai cerut tu această schimbare, poți ignora acest email — parola ta "
        "nu se va modifica.\n\n"
        "Dacă ai cerut resetarea, apasă linkul de mai jos pentru a-ți seta o parolă nouă:\n"
        f"    {reset_url}\n\n"
        "Linkul este valid 1 oră.\n\n"
        "Echipa Utilități.MD"
    )


def send_invitation(to: str, user_name: str, confirm_url: str) -> bool:
    return send_email(
        to,
        "Utilități.MD — Confirmă-ți contul",
        _invitation_body(user_name, confirm_url),
    )


def send_welcome(to: str, user_name: str, username: str, password: str) -> bool:
    return send_email(
        to,
        "Utilități.MD — Contul tău a fost activat",
        _welcome_body(user_name, username, password),
    )


def send_reset_link(to: str, user_name: str, reset_url: str) -> bool:
    return send_email(
        to,
        "Utilități.MD — Resetarea parolei",
        _reset_body(user_name, reset_url),
    )
