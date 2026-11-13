"""OAuth 2.0 Authorization Code with PKCE for Spotify (no client secret needed)."""

from __future__ import annotations

import base64
import hashlib
import secrets
from urllib.parse import urlencode

AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"

# Least privilege: read the user's own and collaborative playlists, and create
# private playlists for export. Nothing else.
SCOPES = ("playlist-read-private", "playlist-read-collaborative", "playlist-modify-private")


def code_verifier() -> str:
    # 64 random bytes -> 86 URL-safe characters, inside the 43..128 range of RFC 7636.
    return base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()


def code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def new_state() -> str:
    return secrets.token_urlsafe(32)


def authorize_url(client_id: str, redirect_uri: str, state: str, verifier: str) -> str:
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": " ".join(SCOPES),
        "code_challenge_method": "S256",
        "code_challenge": code_challenge(verifier),
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def token_request_body(client_id: str, code: str, redirect_uri: str, verifier: str) -> dict[str, str]:
    return {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": verifier,
    }


def refresh_request_body(client_id: str, refresh_token: str) -> dict[str, str]:
    return {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id}


def states_match(expected: str | None, received: str | None) -> bool:
    return bool(expected and received) and secrets.compare_digest(str(expected), str(received))
