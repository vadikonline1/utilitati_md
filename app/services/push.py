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


# --------------------------------------------------------------------------- #
# Firebase Cloud Messaging (HTTP v1)
# --------------------------------------------------------------------------- #
def _load_service_account() -> dict | None:
    """Return the FCM service-account dict, or None if not configured."""
    cached = _FCM_CACHE.get("sa")
    if cached is not None:
        return cached
    raw = os.getenv("FCM_SERVICE_ACCOUNT", "").strip()
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


async def send_push(user_id: int, title: str, body: str) -> int:
    """Send a push to all of a user's devices. Returns tokens attempted."""
    tokens = _user_tokens(user_id)
    if not tokens:
        return 0
    data = {"type": "invoice"}
    sent = 0
    for provider, token in tokens:
        if await _send_one(provider, token, title, body, data):
            sent += 1
    return sent


async def send_push_multi(
    user_ids: list[int], title: str, body: str
) -> dict[str, int]:
    """Send a push to multiple users. Returns {sent, failed}."""
    all_tokens = all_device_tokens()
    total = 0
    failed = 0
    for uid in user_ids:
        for provider, token in all_tokens.get(uid, []):
            ok = await _send_one(provider, token, title, body, {"type": "admin"})
            if ok:
                total += 1
            else:
                failed += 1
    return {"sent": total, "failed": failed}
