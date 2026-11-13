"""Where playlists come from.

``PlaylistSource`` is the seam between the API and data: demo mode reads the
synthetic dataset; live mode (``app.spotify``) will read the signed-in user's
cached Spotify playlists and must enforce ownership in ``get``.
"""

from __future__ import annotations

from collections import Counter
from typing import Protocol

from app.config import Settings
from app.services.demo import Playlist, load_demo_playlists


class PlaylistNotFound(LookupError):
    pass


class PlaylistSource(Protocol):
    mode: str

    def list(self) -> list[Playlist]: ...

    def get(self, playlist_id: str) -> Playlist: ...


class DemoPlaylistSource:
    mode = "demo"

    def __init__(self, settings: Settings) -> None:
        self._playlists = load_demo_playlists(settings.demo_data_path)

    def list(self) -> list[Playlist]:
        return list(self._playlists.values())

    def get(self, playlist_id: str) -> Playlist:
        try:
            return self._playlists[playlist_id]
        except KeyError:
            raise PlaylistNotFound(playlist_id) from None


def facets(playlist: Playlist) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Artists and albums present in the playlist, with entry counts."""
    artist_counts: Counter[str] = Counter()
    artist_names: dict[str, str] = {}
    album_counts: Counter[str] = Counter()
    album_meta: dict[str, tuple[str, str]] = {}
    for e in playlist.entries:
        for a in e.artists:
            artist_counts[a.key] += 1
            artist_names.setdefault(a.key, a.name)
        if e.album and e.album.key and e.album.name:
            album_counts[e.album.key] += 1
            owners = e.album.artists or e.artists[:1]
            album_meta.setdefault(e.album.key, (e.album.name, ", ".join(a.name for a in owners)))
    # Two different artists can share a name; label them by their biggest album here.
    top_album: dict[str, Counter[str]] = {}
    for e in playlist.entries:
        if e.album and e.album.name:
            for a in e.artists:
                top_album.setdefault(a.key, Counter())[e.album.name] += 1
    name_counts = Counter(n for k, n in artist_names.items() if not k.startswith("local-"))

    def detail(key: str) -> str:
        if key.startswith("local-"):
            return "local file"
        if name_counts[artist_names[key]] > 1 and key in top_album:
            return f"appears on {top_album[key].most_common(1)[0][0]}"
        return ""

    artists = [
        {
            "id": k,
            "name": artist_names[k],
            "entry_count": n,
            "is_local": k.startswith("local-"),
            "detail": detail(k),
        }
        for k, n in artist_counts.most_common()
    ]
    albums = [
        {"id": k, "name": album_meta[k][0], "artist_names": album_meta[k][1], "entry_count": n}
        for k, n in album_counts.most_common()
    ]
    return artists, albums
