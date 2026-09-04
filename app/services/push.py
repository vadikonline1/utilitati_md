"""Server-initiated push notifications to registered mobile devices (Expo).

Mobile clients obtain an Expo Push Token (via expo-notifications
getExpoPushTokenAsync) and register it through POST /api/devices/token. When a
new invoice appears we use those tokens to push a notification to the user's
devices, independently of whether the app is currently open.
"""

from __future__ import annotations

import logging

import aiohttp

from ..db import _conn

_LOGGER = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def register_device_token(user_id: int, token: str, platform: str = "android") -> None:
    """Insert or refresh a push token for a user."""
    token = (token or "").strip()
    if not token or token == "ExponentPushToken[InvalidToken]":
        return
    platform = platform if platform in ("android", "ios") else "android"
    with _conn() as conn:
        conn.execute(
            """INSERT INTO device_tokens (user_id, platform, token, last_seen)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(user_id, token)
               DO UPDATE SET last_seen = datetime('now')""",
            (user_id, platform, token),
        )


def user_device_tokens(user_id: int) -> list[str]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT token FROM device_tokens WHERE user_id = ?", (user_id,)
        ).fetchall()
    return [r["token"] for r in rows]


def all_device_tokens() -> dict[int, list[str]]:
    """Return {user_id: [token, ...]} for every registered device."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT user_id, token FROM device_tokens ORDER BY user_id"
        ).fetchall()
    tokens: dict[int, list[str]] = {}
    for r in rows:
        tokens.setdefault(r["user_id"], []).append(r["token"])
    return tokens


def clear_device_tokens(user_id: int) -> None:
    """Remove all push tokens for a user (notifications switched OFF)."""
    with _conn() as conn:
        conn.execute("DELETE FROM device_tokens WHERE user_id = ?", (user_id,))


async def send_push(user_id: int, title: str, body: str) -> int:
    """Send an Expo push to all of a user's devices. Returns tokens attempted."""
    tokens = user_device_tokens(user_id)
    if not tokens:
        return 0
    messages = [
        {
            "to": token,
            "sound": "default",
            "title": title,
            "body": body,
            "data": {"type": "invoice"},
        }
        for token in tokens
    ]
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(EXPO_PUSH_URL, json=messages, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status not in (200, 201):
                    body = await resp.text()
                    _LOGGER.warning("Expo push HTTP %s: %s", resp.status, body[:300])
                return len(messages)
    except Exception:  # noqa: BLE001 - push must never break the sync loop
        _LOGGER.exception("Expo push send failed for user %s", user_id)
        return 0


async def send_push_multi(
    user_ids: list[int], title: str, body: str
) -> dict[str, int]:
    """Send an Expo push to multiple users. Returns {sent, failed}."""
    all_tokens = all_device_tokens()
    total = 0
    failed = 0
    for uid in user_ids:
        tokens = all_tokens.get(uid, [])
        if not tokens:
            continue
        messages = [
            {
                "to": token,
                "sound": "default",
                "title": title,
                "body": body,
                "data": {"type": "admin"},
            }
            for token in tokens
        ]
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    EXPO_PUSH_URL, json=messages,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status not in (200, 201):
                        _LOGGER.warning(
                            "Expo push HTTP %s for user %s: %s",
                            resp.status, uid, (await resp.text())[:200],
                        )
                        failed += len(messages)
                    else:
                        total += len(messages)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Expo push send failed for user %s", uid)
            failed += len(messages)
    return {"sent": total, "failed": failed}