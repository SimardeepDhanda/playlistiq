"""Core data contracts for the filter and shuffle engines.

These models are deliberately independent of Spotify's wire format. The Spotify
adapter (``app.spotify.normalize``) and the demo dataset both produce
``PlaylistEntry`` objects, so the engines never see raw API payloads.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_IDS_PER_LIST = 200
MAX_GAP = 50
MAX_SEED = 2**53 - 1  # largest integer a JavaScript number holds exactly

EntityId = Annotated[str, Field(min_length=1, max_length=200)]


def normalize_name(name: str) -> str:
    """Case-, accent- and punctuation-insensitive form used for name matching."""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def name_key(prefix: str, name: str) -> str:
    """Fallback identity for items without a Spotify ID (for example local files)."""
    return f"{prefix}:{normalize_name(name)}"


class Artist(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str | None = None
    name: str

    @property
    def key(self) -> str:
        return self.id or name_key("local-artist", self.name)


class Album(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str | None = None
    name: str | None = None
    album_type: str | None = None
    artists: tuple[Artist, ...] = ()

    @property
    def key(self) -> str | None:
        if self.id:
            return self.id
        if self.name:
            return name_key("local-album", self.name)
        return None


class PlaylistEntry(BaseModel):
    """One occurrence of an item in a playlist.

    ``entry_id`` identifies the occurrence, not the song: the same ``track_id``
    can appear several times and each occurrence is kept.
    """

    model_config = ConfigDict(frozen=True)

    entry_id: str
    playlist_id: str
    position: int = Field(ge=0)
    track_id: str | None = None
    uri: str | None = None
    name: str
    artists: tuple[Artist, ...] = ()
    album: Album | None = None
    added_at: datetime | None = None
    is_playable: bool | None = None
    is_local: bool = False
    duration_ms: int | None = None

    def artist_keys(self, primary_only: bool = False) -> frozenset[str]:
        artists = self.artists[:1] if primary_only else self.artists
        return frozenset(a.key for a in artists)

    @property
    def album_key(self) -> str | None:
        return self.album.key if self.album else None


class ShuffleMode(StrEnum):
    RANDOM = "random"
    BALANCED = "balanced"
    RECENTLY_ADDED = "recently_added"


IdList = Annotated[list[EntityId], Field(max_length=MAX_IDS_PER_LIST)]


class QuerySpec(BaseModel):
    """Validated description of which entries to keep and how to order them.

    Precedence (documented and tested in ``tests/test_filters.py``):

    * Inside an include list, values are OR-ed.
    * Different categories are AND-ed (artist include AND album include).
    * Exclusions always win: an entry matching any exclusion is removed.
    * An empty include list means "no restriction" for that category.
    * The same ID cannot be both included and excluded; that is rejected as a
      contradiction instead of silently picking a winner.
    """

    model_config = ConfigDict(extra="forbid")

    include_artist_ids: IdList = Field(default_factory=list)
    exclude_artist_ids: IdList = Field(default_factory=list)
    include_album_ids: IdList = Field(default_factory=list)
    exclude_album_ids: IdList = Field(default_factory=list)
    primary_artist_only: bool = False
    shuffle_mode: ShuffleMode = ShuffleMode.BALANCED
    minimum_artist_gap: int = Field(default=1, ge=0, le=MAX_GAP)
    strict_constraints: bool = False
    seed: int | None = Field(default=None, ge=0, le=MAX_SEED)
    recently_added_band_days: int = Field(default=30, ge=0, le=3650)

    @model_validator(mode="after")
    def _no_contradictions(self) -> QuerySpec:
        artist_clash = set(self.include_artist_ids) & set(self.exclude_artist_ids)
        album_clash = set(self.include_album_ids) & set(self.exclude_album_ids)
        problems = []
        if artist_clash:
            problems.append(f"artists both included and excluded: {sorted(artist_clash)}")
        if album_clash:
            problems.append(f"albums both included and excluded: {sorted(album_clash)}")
        if problems:
            raise ValueError("; ".join(problems))
        return self
