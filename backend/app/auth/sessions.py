"""Server-side sessions and the per-user Spotify token provider."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DB

from app.auth import pkce
from app.auth.security import TokenCipher, hash_token, new_session_token
from app.config import Settings
from app.db.models import Session, SpotifyConnection, User
from app.spotify.client import SpotifyAuthError

SESSION_COOKIE = "piq_session"
OAUTH_COOKIE = "piq_oauth"
REFRESH_MARGIN = timedelta(seconds=60)


def _aware(dt: datetime) -> datetime:
    # SQLite returns naive datetimes; everything is stored in UTC.
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def create_session(db: DB, user: User, settings: Settings) -> str:
    token = new_session_token()
    db.add(
        Session(
            token_hash=hash_token(token),
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(days=settings.session_days),
        )
    )
    db.commit()
    return token


def user_for_session(db: DB, token: str | None) -> User | None:
    if not token:
        return None
    row = db.get(Session, hash_token(token))
    if row is None or _aware(row.expires_at) < datetime.now(UTC):
        return None
    return db.get(User, row.user_id)


def end_session(db: DB, token: str | None) -> None:
    if token:
        db.execute(delete(Session).where(Session.token_hash == hash_token(token)))
        db.commit()


def save_tokens(db: DB, user: User, cipher: TokenCipher, token_response: dict[str, Any]) -> SpotifyConnection:
    conn = db.scalar(select(SpotifyConnection).where(SpotifyConnection.user_id == user.id))
    if conn is None:
        conn = SpotifyConnection(user_id=user.id, access_token_enc="", expires_at=datetime.now(UTC))
        db.add(conn)
    conn.access_token_enc = cipher.encrypt(token_response["access_token"])
    if token_response.get("refresh_token"):
        conn.refresh_token_enc = cipher.encrypt(token_response["refresh_token"])
    conn.expires_at = datetime.now(UTC) + timedelta(seconds=int(token_response.get("expires_in", 3600)))
    conn.scopes = token_response.get("scope", conn.scopes or "")
    conn.updated_at = datetime.now(UTC)
    db.commit()
    return conn


async def exchange_code(
    http: httpx.AsyncClient, settings: Settings, code: str, verifier: str
) -> dict[str, Any]:
    assert settings.spotify_client_id
    resp = await http.post(
        pkce.TOKEN_URL,
        data=pkce.token_request_body(
            settings.spotify_client_id, code, settings.spotify_redirect_uri, verifier
        ),
    )
    if resp.status_code != 200:
        raise SpotifyAuthError(resp.status_code, "could not exchange the authorization code")
    result: dict[str, Any] = resp.json()
    return result


class DBTokenProvider:
    """Hands out a valid access token for one user, refreshing it when needed."""

    def __init__(
        self, db: DB, user: User, cipher: TokenCipher, settings: Settings, http: httpx.AsyncClient
    ) -> None:
        self.db, self.user, self.cipher, self.settings, self.http = db, user, cipher, settings, http

    def _conn(self) -> SpotifyConnection:
        conn = self.db.scalar(select(SpotifyConnection).where(SpotifyConnection.user_id == self.user.id))
        if conn is None:
            raise SpotifyAuthError(401, "Spotify is not connected")
        return conn

    async def access_token(self) -> str:
        conn = self._conn()
        if _aware(conn.expires_at) - REFRESH_MARGIN <= datetime.now(UTC):
            return await self.refresh()
        return self.cipher.decrypt(conn.access_token_enc)

    async def refresh(self) -> str:
        conn = self._conn()
        if not conn.refresh_token_enc or not self.settings.spotify_client_id:
            raise SpotifyAuthError(401, "Spotify session expired; please reconnect")
        resp = await self.http.post(
            pkce.TOKEN_URL,
            data=pkce.refresh_request_body(
                self.settings.spotify_client_id, self.cipher.decrypt(conn.refresh_token_enc)
            ),
        )
        if resp.status_code != 200:
            raise SpotifyAuthError(401, "Spotify session expired; please reconnect")
        save_tokens(self.db, self.user, self.cipher, resp.json())
        return self.cipher.decrypt(self._conn().access_token_enc)
