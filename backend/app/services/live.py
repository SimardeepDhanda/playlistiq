"""Live Spotify mode: list, import and cache the signed-in user's playlists."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DB

from app.db.models import PlaylistCache, User
from app.engine.models import PlaylistEntry
from app.services.demo import Playlist
from app.spotify.client import SpotifyClient, SpotifyForbidden
from app.spotify.normalize import normalize_items

PLAYLIST_FIELDS = "id,name,description,owner(id,display_name),collaborative,snapshot_id"


@dataclass(frozen=True)
class SpotifyPlaylistSummary:
    id: str
    name: str
    description: str
    owner_name: str
    item_count: int | None
    readable: bool
    imported: bool
    synced_at: datetime | None


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def readable_by(user: User, playlist: dict[str, Any]) -> bool:
    """Dev Mode only returns items for playlists the user owns or collaborates on."""
    owner = (playlist.get("owner") or {}).get("id")
    return owner == user.spotify_user_id or bool(playlist.get("collaborative"))


def _item_count(playlist: dict[str, Any]) -> int | None:
    block = playlist.get("items") or playlist.get("tracks") or {}
    total = block.get("total") if isinstance(block, dict) else None
    return int(total) if isinstance(total, int) else None


async def list_spotify_playlists(db: DB, user: User, client: SpotifyClient) -> list[SpotifyPlaylistSummary]:
    cached = {
        c.spotify_playlist_id: c
        for c in db.scalars(select(PlaylistCache).where(PlaylistCache.user_id == user.id))
    }
    out = []
    for p in await client.my_playlists():
        if not p or not p.get("id"):
            continue
        c = cached.get(p["id"])
        fresh = c is not None and _aware(c.expires_at) > datetime.now(UTC)
        out.append(
            SpotifyPlaylistSummary(
                id=p["id"],
                name=p.get("name") or "Untitled playlist",
                description=p.get("description") or "",
                owner_name=(p.get("owner") or {}).get("display_name") or "",
                item_count=_item_count(p),
                readable=readable_by(user, p),
                imported=fresh,
                synced_at=c.synced_at if fresh and c else None,
            )
        )
    return out


@dataclass(frozen=True)
class ImportResult:
    playlist_id: str
    name: str
    entry_count: int
    skipped_unavailable: int
    skipped_episodes: int


async def import_playlist(
    db: DB, user: User, client: SpotifyClient, playlist_id: str, cache_hours: int
) -> ImportResult:
    meta = await client.request("GET", f"/playlists/{playlist_id}", params={"fields": PLAYLIST_FIELDS})
    if not readable_by(user, meta):
        raise SpotifyForbidden(
            403,
            "Spotify only lets this app read songs from playlists you own or collaborate on.",
        )
    items = await client.playlist_items(playlist_id)
    report = normalize_items(playlist_id, items)

    db.execute(
        delete(PlaylistCache).where(
            PlaylistCache.user_id == user.id, PlaylistCache.spotify_playlist_id == playlist_id
        )
    )
    now = datetime.now(UTC)
    db.add(
        PlaylistCache(
            user_id=user.id,
            spotify_playlist_id=playlist_id,
            name=meta.get("name") or "Untitled playlist",
            description=meta.get("description") or "",
            snapshot_id=meta.get("snapshot_id"),
            entry_count=len(report.entries),
            skipped_unavailable=report.skipped_unavailable,
            skipped_episodes=report.skipped_episodes,
            entries_json=json.dumps([e.model_dump(mode="json") for e in report.entries]),
            synced_at=now,
            expires_at=now + timedelta(hours=cache_hours),
        )
    )
    db.commit()
    return ImportResult(
        playlist_id=playlist_id,
        name=meta.get("name") or "Untitled playlist",
        entry_count=len(report.entries),
        skipped_unavailable=report.skipped_unavailable,
        skipped_episodes=report.skipped_episodes,
    )


def load_cached(db: DB, user: User, playlist_id: str) -> Playlist | None:
    row = db.scalar(
        select(PlaylistCache).where(
            PlaylistCache.user_id == user.id, PlaylistCache.spotify_playlist_id == playlist_id
        )
    )
    if row is None:
        return None
    if _aware(row.expires_at) <= datetime.now(UTC):
        db.delete(row)  # expired caches are removed, not served
        db.commit()
        return None
    entries = tuple(PlaylistEntry.model_validate(e) for e in json.loads(row.entries_json))
    return Playlist(
        id=playlist_id,
        name=row.name,
        description=row.description,
        entries=entries,
        source="spotify",
    )


def delete_user_data(db: DB, user: User) -> None:
    """Disconnect: remove the user and, by cascade, tokens, sessions, caches and jobs."""
    db.delete(user)
    db.commit()
