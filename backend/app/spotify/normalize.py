"""Convert Spotify playlist item objects into ``PlaylistEntry``.

Handles the February 2026 field rename (``item``, with the deprecated
``track`` as fallback), local files, removed or unavailable tracks (``item``
is null), podcast episodes (skipped and counted), and missing metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.engine.models import Album, Artist, PlaylistEntry


@dataclass
class NormalizeReport:
    entries: list[PlaylistEntry] = field(default_factory=list)
    skipped_unavailable: int = 0
    skipped_episodes: int = 0


def _artist(raw: dict[str, Any]) -> Artist:
    return Artist(id=raw.get("id") or None, name=raw.get("name") or "Unknown artist")


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_items(playlist_id: str, items: list[dict[str, Any]]) -> NormalizeReport:
    report = NormalizeReport()
    for position, raw in enumerate(items):
        obj = raw.get("item") or raw.get("track")
        if not obj:
            report.skipped_unavailable += 1
            continue
        if obj.get("type") == "episode":
            report.skipped_episodes += 1
            continue
        album_raw = obj.get("album") or None
        album = None
        if album_raw:
            album = Album(
                id=album_raw.get("id") or None,
                name=album_raw.get("name") or None,
                album_type=album_raw.get("album_type"),
                artists=tuple(_artist(a) for a in album_raw.get("artists") or []),
            )
        is_local = bool(raw.get("is_local") or obj.get("is_local"))
        report.entries.append(
            PlaylistEntry(
                # Occurrence key: position in the snapshot, so duplicates stay distinct.
                entry_id=f"{playlist_id}:{position}",
                playlist_id=playlist_id,
                position=position,
                track_id=None if is_local else obj.get("id"),
                uri=obj.get("uri"),
                name=obj.get("name") or "Untitled",
                artists=tuple(_artist(a) for a in obj.get("artists") or []),
                album=album,
                added_at=_parse_time(raw.get("added_at")),
                is_playable=obj.get("is_playable"),
                is_local=is_local,
                duration_ms=obj.get("duration_ms"),
            )
        )
    return report
