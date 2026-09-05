"""Server-initiated push notifications to registered mobile devices.

Two push providers are supported:

* ``fcm``  — Google Firebase Cloud Messaging (HTTP v1). The mobile app sends the
             raw FCM registration token (Android: `getDevicePushTokenAsync()`),
             and this server calls FCM directly using a Google service account.
* ``expo`` — Expo push (legacy). Tokens obtained via `getExpoPushTokenAsync`
             are delivered through Expo's relay (`exp.host`), which bridges to
             FCM using the credentials configured in the Expo project console.

The FCM service account is supplied as an environment variable
(`FCM_SERVICE_ACCOUNT` = the service-account JSON, or a path to a file
containing it). It is never stored in the database or committed to source.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time

import aiohttp

from ..db import _conn
from .settings import get_setting

# Deferred import to avoid circular dependency at module load time.
def _notifications_enabled(user_id: int) -> bool:
    from ..auth import is_notifications_enabled
    return is_notifications_enabled(user_id)

_LOGGER = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
FCM_TOKEN_URL = "https://oauth2.googleapis.com/token"
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"

_FCM_CACHE: dict = {}


def register_device_token(
    user_id: int, token: str, platform: str = "android", provider: str = "fcm"
) -> None:
    """Insert or refresh a push token for a user."""
    token = (token or "").strip()
    if not token or token == "ExponentPushToken[InvalidToken]":
        return
    platform = platform if platform in ("android", "ios") else "android"
    provider = provider if provider in ("fcm", "expo") else "fcm"
    with _conn() as conn:
        conn.execute(
            """INSERT INTO device_tokens (user_id, platform, token, provider, last_seen)
               VALUES (?, ?, ?, ?, datetime('now'))
               ON CONFLICT(user_id, token)
               DO UPDATE SET provider = excluded.provider,
                             last_seen = datetime('now')""",
            (user_id, platform, token, provider),
        )
        # A device registers one active token per platform. When the provider
        # changes (server switched fcm<->expo) the old row of the PREVIOUS
        # provider must go, otherwise the stale fcm/expo token would keep
        # failing to deliver (e.g. "FCM_SERVICE_ACCOUNT not configured").
        conn.execute(
            "DELETE FROM device_tokens "
            "WHERE user_id = ? AND platform = ? AND provider != ?",
            (user_id, platform, provider),
        )


def _user_tokens(user_id: int) -> list[tuple[str, str]]:
    """Return [(provider, token), ...] for a user's registered devices."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT provider, token FROM device_tokens WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    return [(r["provider"], r["token"]) for r in rows]


def user_device_tokens(user_id: int) -> list[str]:
    return [token for _, token in _user_tokens(user_id)]


def all_device_tokens() -> dict[int, list[tuple[str, str]]]:
    """Return {user_id: [(provider, token), ...]} for every registered device."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT user_id, provider, token FROM device_tokens ORDER BY user_id"
        ).fetchall()
    tokens: dict[int, list[tuple[str, str]]] = {}
    for r in rows:
        tokens.setdefault(r["user_id"], []).append((r["provider"], r["token"]))
    return tokens


def clear_device_tokens(user_id: int) -> None:
    """Remove all push tokens for a user (notifications switched OFF)."""
    with _conn() as conn:
        conn.execute("DELETE FROM device_tokens WHERE user_id = ?", (user_id,))


def clear_all_device_tokens() -> None:
    """Drop every registered device token (push-provider switch).

    After switching fcm<->expo, stale tokens from the old provider would keep
    failing to deliver; each device re-registers automatically on next launch.
    """
    with _conn() as conn:
        conn.execute("DELETE FROM device_tokens")


# --------------------------------------------------------------------------- #
# Notification history (the in-app / web "bell" feed)
# --------------------------------------------------------------------------- #
def record_notification(
    user_id: int, title: str, body: str, type_: str = "admin"
) -> None:
    """Append a notification to the user's history feed."""
    try:
        with _conn() as conn:
            conn.execute(
                "INSERT INTO notifications (user_id, title, body, type) VALUES (?, ?, ?, ?)",
                (user_id, title, body, type_),
            )
    except Exception:  # noqa: BLE001 - history must never break sending
        _LOGGER.exception("Could not record notification for user %s", user_id)


def list_user_notifications(user_id: int, limit: int = 100) -> list[dict]:
    """Most-recent notifications for a user, newest first."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, title, body, type, read, "
            "datetime(created_at, 'localtime') AS created_at "
            "FROM notifications WHERE user_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (user_id, int(limit)),
        ).fetchall()
    return [dict(r) for r in rows]


def unread_notification_count(user_id: int) -> int:
    """Number of notifications not yet marked as read (bell badge)."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM notifications "
            "WHERE user_id = ? AND read = 0",
            (user_id,),
        ).fetchone()
    return int(row["c"]) if row else 0


def mark_notification_read(user_id: int, notif_id: int) -> bool:
    """Mark one of the user's notifications as read. False if it does not exist."""
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE notifications SET read = 1 "
            "WHERE id = ? AND user_id = ?",
            (notif_id, user_id),
        )
    return cur.rowcount > 0


def mark_all_notifications_read(user_id: int) -> int:
    """Mark every notification of a user as read. Returns affected rows."""
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE notifications SET read = 1 WHERE user_id = ? AND read = 0",
            (user_id,),
        )
    return cur.rowcount


def delete_old_notifications(days: int = 60) -> int:
    """Remove notification history older than `days` days. Returns affected rows."""
    with _conn() as conn:
        cur = conn.execute(
            "DELETE FROM notifications WHERE created_at < datetime('now', ?)",
            (f"-{int(days)} days",),
        )
    return cur.rowcount


# --------------------------------------------------------------------------- #
# Firebase Cloud Messaging (HTTP v1)
# --------------------------------------------------------------------------- #
def _load_service_account() -> dict | None:
    """Return the FCM service-account dict, or None if not configured."""
    cached = _FCM_CACHE.get("sa")
    if cached is not None:
        return cached
    # UI-configured value first (admin settings), then the process environment.
    raw = get_setting("fcm_service_account", "").strip() or os.getenv(
        "FCM_SERVICE_ACCOUNT", ""
    ).strip()
    if not raw:
        return None
    if os.path.isfile(raw):
        with open(raw, "r", encoding="utf-8") as fh:
            raw = fh.read()
    try:
        sa = json.loads(raw)
    except (TypeError, ValueError):
        _LOGGER.error("FCM_SERVICE_ACCOUNT is not valid JSON")
        return None
    _FCM_CACHE["sa"] = sa
    return sa


def clear_fcm_cache() -> None:
    """Drop cached FCM credentials/token (call after the admin changes them)."""
    _FCM_CACHE.clear()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _sign_rs256(private_key_pem: str, message: str) -> bytes:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    key = serialization.load_pem_private_key(
        private_key_pem.encode("utf-8"), password=None
    )
    return key.sign(message.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())


def _create_jwt(sa: dict) -> str:
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = _b64url(
        json.dumps(
            {
                "iss": sa["client_email"],
                "scope": FCM_SCOPE,
                "aud": FCM_TOKEN_URL,
                "iat": now,
                "exp": now + 3600,
            }
        ).encode()
    )
    signing_input = f"{header}.{claims}"
    sig = _sign_rs256(sa["private_key"], signing_input)
    return f"{signing_input}.{_b64url(sig)}"


async def _fcm_access_token() -> str | None:
    now = time.time()
    cached = _FCM_CACHE.get("token")
    if cached and cached.get("exp", 0) > now + 60:
        return cached["value"]
    sa = _load_service_account()
    if not sa:
        return None
    try:
        assertion = _create_jwt(sa)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                sa.get("token_uri") or FCM_TOKEN_URL,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                body = await resp.json()
        token = body.get("access_token")
        if not token:
            _LOGGER.error("FCM OAuth token exchange failed: %s", body)
            return None
        _FCM_CACHE["token"] = {
            "value": token,
            "exp": now + int(body.get("expires_in", 3600)),
        }
        return token
    except Exception:  # noqa: BLE001
        _LOGGER.exception("FCM OAuth token exchange error")
        return None


async def _fcm_send(
    token: str, title: str, body: str, data: dict | None = None
) -> bool:
    """Send one push via FCM HTTP v1. True when FCM accepted (HTTP 200)."""
    sa = _load_service_account()
    if not sa:
        _LOGGER.warning("FCM_SERVICE_ACCOUNT not configured; cannot send FCM push")
        return False
    access = await _fcm_access_token()
    if not access:
        return False
    message: dict = {
        "message": {
            "token": token,
            "notification": {"title": title, "body": body},
            "data": {k: str(v) for k, v in (data or {}).items()},
            "android": {"priority": "high"},
        }
    }
    url = (
        f"https://fcm.googleapis.com/v1/projects/"
        f"{sa['project_id']}/messages:send"
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=message,
                headers={"Authorization": f"Bearer {access}"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    return True
                detail = (await resp.text())[:300]
                if resp.status == 404 or "UNREGISTERED" in detail:
                    _LOGGER.warning("FCM token unregistered: %s", detail)
                else:
                    _LOGGER.warning("FCM push HTTP %s: %s", resp.status, detail)
                return False
    except Exception:  # noqa: BLE001
        _LOGGER.exception("FCM push send error")
        return False


async def _expo_send(token: str, title: str, body: str, data: dict | None) -> bool:
    """Send one push via the Expo relay. True when Expo accepted (2xx)."""
    message = {
        "to": token,
        "sound": "default",
        "title": title,
        "body": body,
        "data": data or {},
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                EXPO_PUSH_URL,
                json=[message],
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                return resp.status in (200, 201)
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Expo push send failed")
        return False


async def _send_one(
    provider: str, token: str, title: str, body: str, data: dict | None
) -> bool:
    if provider == "fcm":
        return await _fcm_send(token, title, body, data)
    return await _expo_send(token, title, body, data)


async def send_push(
    user_id: int, title: str, body: str, type_: str = "general", *, record: bool = True
) -> int:
    """Send a push to all of a user's devices. Returns tokens attempted.

    When ``record`` is True (default) a delivered push is also appended to the
    user's in-app notification feed (the bell). Callers that already wrote the
    feed row themselves pass ``record=False`` to avoid duplicates.
    """
    if not _notifications_enabled(user_id):
        return 0
    tokens = _user_tokens(user_id)
    if not tokens:
        return 0
    data = {"type": type_}
    sent = 0
    for provider, token in tokens:
        if await _send_one(provider, token, title, body, data):
            sent += 1
    if sent and record:
        record_notification(user_id, title, body, type_)
    return sent


async def send_push_multi(
    user_ids: list[int], title: str, body: str, type_: str = "admin"
) -> dict[str, int]:
    """Send a push to multiple users. Returns {sent, failed}."""
    from ..auth import is_notifications_enabled

    active_ids = [uid for uid in user_ids if is_notifications_enabled(uid)]
    all_tokens = all_device_tokens()
    total = 0
    failed = 0
    for uid in active_ids:
        uid_sent = 0
        for provider, token in all_tokens.get(uid, []):
            ok = await _send_one(provider, token, title, body, {"type": type_})
            if ok:
                total += 1
                uid_sent += 1
            else:
                failed += 1
        if uid_sent:
            record_notification(uid, title, body, type_)
    return {"sent": total, "failed": failed}
