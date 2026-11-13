from __future__ import annotations

from collections.abc import Sequence

import pytest

from app.config import get_settings
from app.engine.models import Album, Artist, PlaylistEntry
from app.services.demo import Playlist, load_demo_playlists


@pytest.fixture(scope="session")
def demo() -> dict[str, Playlist]:
    return load_demo_playlists(get_settings().demo_data_path)


@pytest.fixture(scope="session")
def big(demo: dict[str, Playlist]) -> Playlist:
    return demo["demo-late-night"]


def ids_by_name(entries: Sequence[PlaylistEntry], name: str, kind: str = "artist") -> list[str]:
    found: set[str] = set()
    for e in entries:
        if kind == "artist":
            found.update(a.key for a in e.artists if a.name == name)
        elif e.album and e.album.name == name and e.album.key:
            found.add(e.album.key)
    assert found, f"{kind} {name!r} not in fixture"
    return sorted(found)


def make_entry(
    pos: int,
    artists: Sequence[str],
    album: str | None = "Album",
    track_id: str | None = None,
    pid: str = "p",
) -> PlaylistEntry:
    return PlaylistEntry(
        entry_id=f"{pid}:{pos}",
        playlist_id=pid,
        position=pos,
        track_id=track_id or f"t{pos}",
        uri=f"demo:track:{track_id or f't{pos}'}",
        name=f"Song {pos}",
        artists=tuple(Artist(id=f"ar-{a}", name=a) for a in artists),
        album=Album(id=f"al-{album}", name=album) if album else None,
    )


def make_entries(artist_seq: Sequence[str | tuple[str, ...]]) -> list[PlaylistEntry]:
    return [make_entry(i, (a,) if isinstance(a, str) else a) for i, a in enumerate(artist_seq)]
