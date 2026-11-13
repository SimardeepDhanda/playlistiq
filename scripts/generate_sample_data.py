"""Generate the synthetic demo dataset in sample_data/demo_playlists.json.

Every artist, album and track here is fictional and generated from word lists.
Nothing is taken from Spotify. The dataset deliberately includes the awkward
cases real playlists have: duplicate entries, collaborations, two different
artists with the same name, album title collisions, deluxe and remastered
editions, a compilation, local files with no IDs, unavailable tracks, and one
artist who dominates the playlist.

Run from the repository root:  python scripts/generate_sample_data.py
The output is deterministic (fixed seed), so re-running produces the same file.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

SEED = 20261113
OUT = Path(__file__).resolve().parent.parent / "sample_data" / "demo_playlists.json"

WORDS_A = [
    "Midnight",
    "Paper",
    "Golden",
    "Quiet",
    "Electric",
    "Hollow",
    "Velvet",
    "Silver",
    "Broken",
    "Northern",
    "Slow",
    "Neon",
    "Cold",
    "Bright",
    "Lonely",
    "Wild",
    "Distant",
    "Open",
    "Last",
    "Lucky",
    "Fading",
    "Restless",
    "Crimson",
    "Soft",
    "Sunday",
    "Heavy",
    "Little",
    "Secret",
]
WORDS_B = [
    "Roads",
    "Signals",
    "Rooms",
    "Rivers",
    "Letters",
    "Engines",
    "Hearts",
    "Windows",
    "Static",
    "Weather",
    "Gardens",
    "Echoes",
    "Satellites",
    "Mirrors",
    "Avenues",
    "Fires",
    "Motels",
    "Highways",
    "Tides",
    "Lanterns",
    "Promises",
    "Shadows",
    "Summers",
    "Waves",
    "Ghosts",
]
TITLE_TEMPLATES = [
    "{a} {b}",
    "{b}",
    "{a} {b} (Interlude)",
    "No More {b}",
    "{a}",
    "Back to the {b}",
    "{a} Again",
    "Talk About {b}",
    "{a} {b}, Pt. 2",
    "Call Me {a}",
    "{b} in {a}",
]

# (artist name, popularity weight in the big playlist, albums: [(title, type, n_tracks)])
ARTISTS: list[tuple[str, float, list[tuple[str, str, int]]]] = [
    (
        "Marlo Vance",
        18.0,
        [
            ("Overlook", "album", 20),
            ("Overlook (Deluxe)", "album", 6),
            ("Northern Lights", "album", 18),
            ("After Hours Club", "album", 16),
            ("Southside Tapes", "album", 14),
            ("Late Calls", "single", 2),
        ],
    ),
    (
        "J. Calder",
        9.0,
        [
            ("The Long Season", "album", 12),
            ("Porch Light", "album", 14),
            ("Porch Light (Remastered 2021)", "album", 14),
            ("Roads Home", "album", 13),
        ],
    ),
    ("Ivy Calder", 2.0, [("Glasshouse", "album", 11), ("Moth", "single", 1)]),
    ("Nia Solstice", 4.0, [("Homecoming", "album", 12), ("Saltwater", "album", 10)]),
    ("The Static Hours", 3.5, [("Homecoming", "album", 11), ("Night Shift", "album", 10)]),
    ("Kiro", 4.0, [("Gold Coast", "album", 12), ("Paper Planes Club", "album", 10)]),
    ("Gold Coast", 2.5, [("Harbor Lights", "album", 10)]),
    ("Echo", 2.5, [("Feedback Loops", "album", 10)]),  # indie rock Echo
    ("Echo", 2.0, [("Waveform", "album", 9)]),  # electronic Echo, different artist
    ("Sable & Tide", 3.0, [("Undertow", "album", 11)]),
    ("Lumen Hart", 3.0, [("Afterglow", "album", 12), ("Signals", "album", 9)]),
    ("Vesper Lane", 2.5, [("Blue Hour", "album", 10)]),
    ("Ottoline", 2.0, [("Wax & Wire", "album", 10)]),
    ("Brasswood", 2.0, [("Low Country", "album", 10)]),
    ("Rue Morrow", 2.0, [("Small Hours", "album", 9)]),
    ("Cass Ferro", 2.0, [("Iron Bloom", "album", 10)]),
    ("Indigo Ravel", 1.8, [("Thread", "album", 9)]),
    ("Polar Twin", 1.8, [("Northbound", "album", 10)]),
    ("Hollis Gray", 1.8, [("Field Notes", "album", 10)]),
    ("Juno Park", 1.8, [("Satellite Kids", "album", 10)]),
    ("Mae Arden", 1.6, [("Kitchen Radio", "album", 9)]),
    ("Dusk Theory", 1.6, [("Proofs", "album", 9)]),
    ("Low Orbit", 1.6, [("Re-Entry", "album", 9)]),
    ("Tamsin Vale", 1.5, [("Lowlands", "album", 9)]),
    ("Kai Okonjo", 1.5, [("Lagos to Leeds", "album", 10)]),
    ("Pilot Season", 1.5, [("Test Episodes", "album", 9)]),
    ("Harlow Quinn", 1.4, [("Velvet Static", "album", 9)]),
    ("Arlo Banks", 1.4, [("Riverbed", "album", 9)]),
    ("Sora Lin", 1.4, [("Cloud Atlas Road", "album", 9)]),
    ("The Lanterns", 1.3, [("Wicks", "album", 9)]),
    ("Femi Adair", 1.3, [("Blue Note Sunday", "album", 9)]),
    ("Willa Stone", 1.3, [("Quarry", "album", 9)]),
    ("Paris Rook", 1.2, [("Checkmate", "album", 8)]),
    ("Nico Varga", 1.2, [("Budapest Nights", "album", 8)]),
    ("Delta Rae Fox", 1.2, [("Mud & Gold", "album", 8)]),
    ("Otis Crane", 1.1, [("Long Neck", "album", 8)]),
    ("Leila Moreau", 1.1, [("Rive Gauche", "album", 8)]),
    ("Grey Atlas", 1.1, [("Cartography", "album", 8)]),
    ("Bastian Cole", 1.0, [("Night Ferry", "album", 8)]),
    ("June & The Hollows", 1.0, [("Tall Grass", "album", 8)]),
    ("Remy Sato", 1.0, [("Tokyo Drift Wood", "album", 8)]),
    ("Calloway Sound", 1.0, [("Brass Tacks", "album", 8)]),
    ("Yara Benn", 0.9, [("Desert Bloom", "album", 8)]),
    ("Fable Drive", 0.9, [("Once Upon", "album", 8)]),
    ("Theo Marsh", 0.9, [("Wetlands", "album", 8)]),
    ("Aurora Vey", 0.9, [("Polar Night", "album", 8)]),
    ("Mint Condition Club", 0.8, [("Shrinkwrap", "album", 8)]),
    ("Silas Reed", 0.8, [("Woodwind", "album", 8)]),
    ("Kestrel", 0.8, [("Hover", "album", 8)]),
    ("Opal Rivers", 0.8, [("Gemstone", "album", 8)]),
    ("Zane Holloway", 0.7, [("Hollow Point", "album", 8)]),
    ("Mira Sol", 0.7, [("Equinox", "album", 8)]),
    ("Cobalt Youth", 0.7, [("Teen Spirit Radio", "album", 8)]),
    ("Ezra Bloom", 0.7, [("Seedlings", "album", 8)]),
    ("Petra Lune", 0.6, [("Moonlit", "album", 8)]),
    ("Hugo Ash", 0.6, [("Cinders", "album", 8)]),
    ("Rosa Vega", 0.6, [("Camino", "album", 8)]),
    ("Atlas & Wren", 0.6, [("Migration", "album", 8)]),
    ("Saffron Hill", 0.5, [("Spice Route", "album", 8)]),
    ("Noel Archer", 0.5, [("Bullseye", "album", 8)]),
]

COLLAB_PAIRS = [
    ("Marlo Vance", "J. Calder", 10),
    ("Marlo Vance", "Kiro", 6),
    ("J. Calder", "Nia Solstice", 4),
    ("Lumen Hart", "Sable & Tide", 3),
    ("Marlo Vance", "Ivy Calder", 2),
    ("Kiro", "Gold Coast", 3),
    ("Vesper Lane", "Ottoline", 2),
    ("J. Calder", "Kai Okonjo", 2),
]


def main() -> None:
    rng = random.Random(SEED)
    artist_rows: list[dict[str, str]] = []
    artist_by_name: dict[str, list[dict[str, str]]] = {}
    albums: list[dict[str, object]] = []
    tracks: list[dict[str, object]] = []
    weights: dict[str, float] = {}
    used_titles: set[str] = set()
    used_album_names = {title for _, _, specs in ARTISTS for title, _, _ in specs}

    def title() -> str:
        for _ in range(100):
            t = rng.choice(TITLE_TEMPLATES).format(a=rng.choice(WORDS_A), b=rng.choice(WORDS_B))
            if t not in used_titles or rng.random() < 0.05:
                used_titles.add(t)
                return t
        return t

    def new_track(name: str, artists: list[dict[str, str]], album: dict[str, object]) -> None:
        tracks.append(
            {
                "id": f"demo-track-{len(tracks) + 1:05d}",
                "name": name,
                "artists": artists,
                "album": album,
                "duration_ms": rng.randint(120_000, 330_000),
                "is_playable": rng.random() > 0.01,
            }
        )

    for name, weight, album_specs in ARTISTS:
        album_specs = list(album_specs)
        # Pad each catalog so the big playlist can reach 2,000+ distinct tracks while
        # keeping the skew: heavier artists get more albums.
        target = int(15 + weight * 14)
        while sum(n for _, _, n in album_specs) < target:
            padded = f"{rng.choice(WORDS_A)} {rng.choice(WORDS_B)}"
            if padded in used_album_names:
                continue  # only the deliberate collisions above may repeat a title
            used_album_names.add(padded)
            album_specs.append((padded, "album", rng.randint(9, 14)))
        artist = {"id": f"demo-artist-{len(artist_rows) + 1:03d}", "name": name}
        artist_rows.append(artist)
        artist_by_name.setdefault(name, []).append(artist)
        weights[artist["id"]] = weight
        base_titles: dict[str, list[str]] = {}
        for album_name, album_type, n_tracks in album_specs:
            album = {
                "id": f"demo-album-{len(albums) + 1:03d}",
                "name": album_name,
                "album_type": album_type,
                "artists": [artist],
            }
            albums.append(album)
            base = album_name.split(" (")[0]
            if base in base_titles:
                # Editions reuse the original track titles, like real deluxe/remaster releases.
                originals = base_titles[base]
                names = (
                    originals[:n_tracks] if "Remaster" in album_name else [title() for _ in range(n_tracks)]
                )
                if "Remaster" in album_name:
                    names = [f"{t} - Remastered 2021" for t in names]
            else:
                names = [title() for _ in range(n_tracks)]
                base_titles[base] = names
            for t in names:
                new_track(t, [artist], album)

    # Collaborations: credited to both artists, released on the first artist's album.
    for lead, guest, count in COLLAB_PAIRS:
        a, b = artist_by_name[lead][0], artist_by_name[guest][0]
        lead_albums = [al for al in albums if al["artists"] == [a] and al["album_type"] == "album"]
        for _ in range(count):
            new_track(f"{title()} (feat. {guest})", [a, b], rng.choice(lead_albums))

    # A compilation album with tracks by several artists.
    various = {"id": "demo-artist-999", "name": "Various Artists"}
    comp = {
        "id": f"demo-album-{len(albums) + 1:03d}",
        "name": "Summer Sessions Vol. 2",
        "album_type": "compilation",
        "artists": [various],
    }
    albums.append(comp)
    for artist in rng.sample(artist_rows[:30], 14):
        new_track(f"{title()} (Live Session)", [artist], comp)

    # ---------------------------------------------------------------- playlists
    def track_weight(t: dict[str, object]) -> float:
        arts = t["artists"]
        assert isinstance(arts, list)
        return max(weights.get(a["id"], 1.0) for a in arts)

    start = datetime(2019, 3, 1, tzinfo=UTC)
    span_days = (datetime(2026, 10, 30, tzinfo=UTC) - start).days

    def entry(
        t: dict[str, object] | None, pid: str, pos: int, local: dict[str, object] | None = None
    ) -> dict[str, object]:
        added = start + timedelta(days=rng.random() ** 0.7 * span_days, seconds=rng.randint(0, 86399))
        base: dict[str, object] = {
            "entry_id": f"{pid}:{pos}",
            "playlist_id": pid,
            "position": pos,
            "added_at": added.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if local is not None:
            return {**base, **local}
        assert t is not None
        return {
            **base,
            "track_id": t["id"],
            "uri": f"demo:track:{t['id']}",
            "name": t["name"],
            "artists": t["artists"],
            "album": t["album"],
            "is_playable": t["is_playable"],
            "is_local": False,
            "duration_ms": t["duration_ms"],
        }

    def weighted_sample(pool: list[dict[str, object]], k: int) -> list[dict[str, object]]:
        # Weighted sampling without replacement (Efraimidis-Spirakis keys).
        keyed = sorted(pool, key=lambda t: rng.random() ** (1.0 / track_weight(t)), reverse=True)
        return keyed[:k]

    playlists = []

    # 1. The big one: about 2,400 entries with duplicates and local files.
    pid = "demo-late-night"
    picked = weighted_sample(tracks, min(len(tracks), 2360))
    rng.shuffle(picked)
    dupes = rng.sample(picked, 30)
    for d in dupes:
        picked.insert(rng.randrange(len(picked)), d)
    entries = [entry(t, pid, i) for i, t in enumerate(picked)]
    locals_ = [
        {
            "name": "Garage Jam 1",
            "artists": [{"id": None, "name": "Basement Static"}],
            "album": {"id": None, "name": "Basement Tapes", "album_type": None, "artists": []},
        },
        {
            "name": "Garage Jam 2",
            "artists": [{"id": None, "name": "Basement Static"}],
            "album": {"id": None, "name": "Basement Tapes", "album_type": None, "artists": []},
        },
        {"name": "Voice Memo 14", "artists": [], "album": None},
        {"name": "Untitled Bounce", "artists": [{"id": None, "name": "Marlo Vance"}], "album": None},
    ]
    for loc in locals_:
        pos = len(entries)
        entries.append(
            entry(
                None,
                pid,
                pos,
                {
                    "track_id": None,
                    "uri": None,
                    "is_playable": False,
                    "is_local": True,
                    "duration_ms": None,
                    **loc,
                },
            )
        )
    playlists.append(
        {
            "id": pid,
            "name": "Late Night Rotation",
            "description": "Synthetic demo playlist: about 2,400 entries, one dominant artist, "
            "duplicates, collaborations and local files.",
            "entries": entries,
        }
    )

    # 2. A medium playlist.
    pid = "demo-road-trip"
    picked = weighted_sample([t for t in tracks if track_weight(t) < 5], 180)
    playlists.append(
        {
            "id": pid,
            "name": "Road Trip Mix",
            "description": "Synthetic demo playlist: 180 entries spread across many artists.",
            "entries": [entry(t, pid, i) for i, t in enumerate(picked)],
        }
    )

    # 3. Single artist, to show what balanced mode can and cannot do.
    pid = "demo-calder-deep-dive"
    calder = artist_by_name["J. Calder"][0]
    solo = [t for t in tracks if t["artists"] == [calder]]
    picked = rng.sample(solo, 45)
    playlists.append(
        {
            "id": pid,
            "name": "Calder Deep Dive",
            "description": "Synthetic demo playlist: 45 entries, all by one artist.",
            "entries": [entry(t, pid, i) for i, t in enumerate(picked)],
        }
    )

    payload = {
        "generated_by": "scripts/generate_sample_data.py",
        "seed": SEED,
        "notice": "Synthetic data. All artists, albums and tracks are fictional.",
        "playlists": playlists,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
    sizes = ", ".join(f"{p['name']}: {len(p['entries'])}" for p in playlists)
    print(f"Wrote {OUT} ({sizes})")


if __name__ == "__main__":
    main()
