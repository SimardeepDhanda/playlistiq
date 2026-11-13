"""Demo mode: synthetic playlists loaded from sample_data/, no network access."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.engine.models import PlaylistEntry


@dataclass(frozen=True)
class Playlist:
    id: str
    name: str
    description: str
    entries: tuple[PlaylistEntry, ...]
    source: str = "demo"

    @property
    def entry_count(self) -> int:
        return len(self.entries)


@lru_cache(maxsize=4)
def load_demo_playlists(path: Path) -> dict[str, Playlist]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    playlists: dict[str, Playlist] = {}
    for p in raw["playlists"]:
        entries = tuple(PlaylistEntry.model_validate(e) for e in p["entries"])
        playlists[p["id"]] = Playlist(
            id=p["id"], name=p["name"], description=p["description"], entries=entries
        )
    return playlists
