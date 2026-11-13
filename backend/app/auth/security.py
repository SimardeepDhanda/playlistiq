"""Token encryption, signed short-lived cookies, and session tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


def _derive(secret: str, purpose: str) -> bytes:
    return hashlib.sha256(f"playlistiq:{purpose}:{secret}".encode()).digest()


class TokenCipher:
    """Encrypts OAuth tokens at rest (Fernet: AES-128-CBC + HMAC-SHA256)."""

    def __init__(self, secret: str) -> None:
        self._fernet = Fernet(base64.urlsafe_b64encode(_derive(secret, "tokens")))

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("stored token cannot be decrypted (secret changed?)") from exc


def sign(secret: str, payload: dict[str, Any]) -> str:
    body = base64.urlsafe_b64encode(json.dumps({**payload, "iat": int(time.time())}).encode())
    mac = hmac.new(_derive(secret, "cookie"), body, hashlib.sha256).hexdigest()
    return f"{body.decode()}.{mac}"


def unsign(secret: str, value: str | None, max_age: int) -> dict[str, Any] | None:
    if not value or "." not in value:
        return None
    body, mac = value.rsplit(".", 1)
    expected = hmac.new(_derive(secret, "cookie"), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, expected):
        return None
    try:
        data: dict[str, Any] = json.loads(base64.urlsafe_b64decode(body.encode()))
    except ValueError:
        return None
    if time.time() - int(data.get("iat", 0)) > max_age:
        return None
    return data


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
