from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Path

from app.config import Settings, get_settings
from app.services.demo import Playlist
from app.services.playlists import DemoPlaylistSource, PlaylistNotFound, PlaylistSource

PlaylistId = Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]


def get_source(settings: Annotated[Settings, Depends(get_settings)]) -> PlaylistSource:
    # Live Spotify sources are selected here once a user session exists (milestone M2).
    return DemoPlaylistSource(settings)


SourceDep = Annotated[PlaylistSource, Depends(get_source)]


def get_playlist(playlist_id: PlaylistId, source: SourceDep) -> Playlist:
    try:
        return source.get(playlist_id)
    except PlaylistNotFound:
        raise HTTPException(status_code=404, detail="Playlist not found") from None


PlaylistDep = Annotated[Playlist, Depends(get_playlist)]
