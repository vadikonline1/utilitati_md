"""Telegram bot integration: webhook registration + sending messages.

The admin can register the bot webhook ("Set bot") from the /admin dashboard so
Telegram delivers updates (e.g. a user sending /start) to our /telegram/webhook
endpoint, letting a user learn their chat id. When a user has a chat id saved in
their profile, password-reset links are also pushed to Telegram (in addition to
email).

We use the plain HTTP Bot API over aiohttp (already a dependency).
"""

from __future__ import annotations

import logging

import aiohttp

from .settings import get_setting

_LOGGER = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/{method}"

# Reset-link messages shown in Telegram when a user requests a password reset.
_RESET_TEXT = {
    "ro": "Utilități.MD — Resetarea parolei\n\n"
          "Apasă pe linkul de mai jos pentru a-ți seta o parolă nouă "
          "(valabil 1 oră):\n{url}",
    "ru": "Utilități.MD — Сброс пароля\n\n"
          "Нажмите на ссылку ниже, чтобы задать новый пароль "
          "(действует 1 час):\n{url}",
    "en": "Utilități.MD — Password reset\n\n"
          "Click the link below to set a new password (valid 1 hour):\n{url}",
}

_DEFAULT_LANG = "ro"


def telegram_configured() -> bool:
    """True when a bot token is configured (env or admin panel)."""
    return bool(get_setting("telegram_token"))


def _token() -> str:
    return get_setting("telegram_token", "").strip()


async def _call(method: str, **payload) -> dict | None:
    """POST JSON to a Telegram Bot API method. Returns the parsed reply."""
    token = _token()
    if not token:
        return None
    url = _API.format(token=token, method=method)
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                try:
                    return await resp.json()
                except Exception:  # noqa: BLE001
                    return {"ok": False, "description": f"HTTP {resp.status}"}
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Telegram API call %s failed", method)
        return None


async def set_webhook(webhook_url: str) -> tuple[bool, str]:
    """Register the webhook URL for the configured bot. Returns (ok, message)."""
    result = await _call("setWebhook", url=webhook_url)
    if not result:
        return False, "Telegram API unreachable"
    if result.get("ok"):
        return True, str(result.get("description") or "ok")
    return False, str(result.get("description") or "failed")


async def send_message(chat_id, text: str) -> bool:
    """Send a plain-text message to a chat. Returns True on success."""
    result = await _call("sendMessage", chat_id=chat_id, text=text)
    return bool(result and result.get("ok"))


def _chat_ids(csv_value: str) -> list:
    """Parse a comma/newline-separated list of chat ids into clean strings."""
    out = []
    for part in str(csv_value or "").replace(",", "\n").split():
        part = part.strip()
        if part:
            out.append(part)
    return out


async def send_reset_link_to_chats(
    chat_ids_csv: str, reset_url: str, lang: str = _DEFAULT_LANG
) -> None:
    """Send the password-reset link to every chat id the user configured."""
    text = _RESET_TEXT.get(lang, _RESET_TEXT[_DEFAULT_LANG]).format(url=reset_url)
    for chat_id in _chat_ids(chat_ids_csv):
        await send_message(chat_id, text)
