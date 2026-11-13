"""Pure filtering over normalized playlist entries.

Filtering never reorders: the result keeps the playlist's original order so the
shuffle step is the only place ordering changes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.engine.models import PlaylistEntry, QuerySpec


@dataclass(frozen=True)
class FilterResult:
    matched: list[PlaylistEntry]
    total: int
    reasons: dict[str, list[str]] = field(default_factory=dict)
    removed_by_exclusion: int = 0

    @property
    def match_count(self) -> int:
        return len(self.matched)


def _explain(
    entry: PlaylistEntry,
    spec: QuerySpec,
    inc_artists: set[str],
    inc_albums: set[str],
) -> list[str]:
    reasons: list[str] = []
    artists = entry.artists[:1] if spec.primary_artist_only else entry.artists
    hits = [a.name for a in artists if a.key in inc_artists]
    if hits:
        reasons.append("artist: " + ", ".join(hits))
    if entry.album and entry.album_key in inc_albums:
        reasons.append(f"album: {entry.album.name}")
    if not reasons:
        reasons.append("no include rules (all entries eligible)")
    return reasons


def apply_filters(entries: Sequence[PlaylistEntry], spec: QuerySpec, explain: bool = False) -> FilterResult:
    inc_artists = set(spec.include_artist_ids)
    exc_artists = set(spec.exclude_artist_ids)
    inc_albums = set(spec.include_album_ids)
    exc_albums = set(spec.exclude_album_ids)

    matched: list[PlaylistEntry] = []
    reasons: dict[str, list[str]] = {}
    removed_by_exclusion = 0

    for entry in entries:
        artist_keys = entry.artist_keys(spec.primary_artist_only)
        album_key = entry.album_key

        if inc_artists and not (artist_keys & inc_artists):
            continue
        if inc_albums and album_key not in inc_albums:
            continue
        if (artist_keys & exc_artists) or (album_key is not None and album_key in exc_albums):
            removed_by_exclusion += 1
            continue

        matched.append(entry)
        if explain:
            reasons[entry.entry_id] = _explain(entry, spec, inc_artists, inc_albums)

    return FilterResult(
        matched=matched,
        total=len(entries),
        reasons=reasons,
        removed_by_exclusion=removed_by_exclusion,
    )
