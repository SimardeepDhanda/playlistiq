from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Path, Request
from sqlalchemy.orm import Session as DB

from app.auth.security import TokenCipher
from app.auth.sessions import SESSION_COOKIE, DBTokenProvider, user_for_session
from app.config import Settings, get_settings
from app.db.models import User
from app.db.session import get_db
from app.services.demo import Playlist
from app.services.playlists import (
    CombinedPlaylistSource,
    DemoPlaylistSource,
    PlaylistNotFound,
    PlaylistNotImported,
    PlaylistSource,
)
from app.spotify.client import SpotifyClient

PlaylistId = Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
SettingsDep = Annotated[Settings, Depends(get_settings)]
DBDep = Annotated[DB, Depends(get_db)]


def get_current_user(request: Request, db: DBDep) -> User | None:
    return user_for_session(db, request.cookies.get(SESSION_COOKIE))


OptionalUser = Annotated[User | None, Depends(get_current_user)]


def require_user(user: OptionalUser) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Connect Spotify first")
    return user


UserDep = Annotated[User, Depends(require_user)]


async def get_http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
        yield client


HttpDep = Annotated[httpx.AsyncClient, Depends(get_http)]


def get_cipher(settings: SettingsDep) -> TokenCipher:
    return TokenCipher(settings.secret())


CipherDep = Annotated[TokenCipher, Depends(get_cipher)]


def get_spotify(
    user: UserDep, db: DBDep, settings: SettingsDep, cipher: CipherDep, http: HttpDep
) -> SpotifyClient:
    return SpotifyClient(DBTokenProvider(db, user, cipher, settings, http), http)


SpotifyDep = Annotated[SpotifyClient, Depends(get_spotify)]


def get_source(settings: SettingsDep, db: DBDep, user: OptionalUser) -> PlaylistSource:
    return CombinedPlaylistSource(DemoPlaylistSource(settings), db, user)


SourceDep = Annotated[PlaylistSource, Depends(get_source)]


async def get_playlist(playlist_id: PlaylistId, source: SourceDep) -> Playlist:
    try:
        return await source.get(playlist_id)
    except PlaylistNotImported:
        raise HTTPException(status_code=409, detail="Import this playlist first") from None
    except PlaylistNotFound:
        raise HTTPException(status_code=404, detail="Playlist not found") from None


PlaylistDep = Annotated[Playlist, Depends(get_playlist)]
