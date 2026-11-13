"""Response models for the HTTP API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.engine.models import Album, Artist, QuerySpec, ShuffleMode
from app.engine.query_parser import ParseResult


class PlaylistSummary(BaseModel):
    id: str
    name: str
    description: str
    entry_count: int
    source: str


class SpotifyPlaylistOut(BaseModel):
    id: str
    name: str
    description: str
    owner_name: str
    item_count: int | None
    readable: bool
    imported: bool
    synced_at: datetime | None


class ImportOut(BaseModel):
    playlist_id: str
    name: str
    entry_count: int
    skipped_unavailable: int
    skipped_episodes: int


class PlaylistList(BaseModel):
    mode: str
    playlists: list[PlaylistSummary]


class EntryOut(BaseModel):
    entry_id: str
    position: int
    track_id: str | None
    uri: str | None
    name: str
    artists: tuple[Artist, ...]
    album: Album | None
    added_at: datetime | None
    is_playable: bool | None
    is_local: bool
    duration_ms: int | None


class TracksPage(BaseModel):
    playlist_id: str
    total: int
    offset: int
    limit: int
    items: list[EntryOut]


class ArtistFacet(BaseModel):
    id: str
    name: str
    entry_count: int
    is_local: bool
    detail: str = ""


class AlbumFacet(BaseModel):
    id: str
    name: str
    artist_names: str
    entry_count: int


class Facets(BaseModel):
    playlist_id: str
    artists: list[ArtistFacet]
    albums: list[AlbumFacet]


class QueueItem(EntryOut):
    queue_position: int
    match_reasons: list[str] = Field(default_factory=list)


class ViolationOut(BaseModel):
    position: int
    entry_id: str
    conflicting_position: int
    shared_artists: tuple[str, ...]


class OrderMetricsOut(BaseModel):
    adjacent_overlap_rate: float
    same_artist_pairs_within_3: int
    same_artist_pairs_within_5: int


class Timing(BaseModel):
    filter_ms: float
    shuffle_ms: float
    total_ms: float


class PreviewResponse(BaseModel):
    playlist_id: str
    spec: QuerySpec
    total_entries: int
    match_count: int
    removed_by_exclusion: int
    mode: ShuffleMode
    seed: int
    status: str
    applied_rules: list[str]
    notes: list[str]
    violations: list[ViolationOut]
    metrics: OrderMetricsOut
    timing: Timing
    queue: list[QueueItem]


class ParseRequest(BaseModel):
    playlist_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    text: str = Field(min_length=1, max_length=500)


class ParseResponse(ParseResult):
    pass
