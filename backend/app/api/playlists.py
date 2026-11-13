from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import DBDep, PlaylistDep, PlaylistId, SettingsDep, SourceDep, SpotifyDep, UserDep
from app.api.schemas import (
    EntryOut,
    Facets,
    ImportOut,
    OrderMetricsOut,
    PlaylistList,
    PlaylistSummary,
    PreviewResponse,
    QueueItem,
    SpotifyPlaylistOut,
    Timing,
    TracksPage,
    ViolationOut,
)
from app.engine.filters import apply_filters
from app.engine.metrics import summarize
from app.engine.models import QuerySpec, ShuffleMode
from app.engine.shuffle import shuffle
from app.services.demo import Playlist
from app.services.live import import_playlist, list_spotify_playlists
from app.services.playlists import facets

router = APIRouter(prefix="/api/playlists", tags=["playlists"])


@router.get("", response_model=PlaylistList)
async def list_playlists(source: SourceDep) -> PlaylistList:
    return PlaylistList(
        mode=source.mode,
        playlists=[
            PlaylistSummary(
                id=p.id,
                name=p.name,
                description=p.description,
                entry_count=p.entry_count,
                source=p.source,
            )
            for p in await source.list()
        ],
    )


@router.get("/spotify", response_model=list[SpotifyPlaylistOut])
async def list_spotify(user: UserDep, db: DBDep, client: SpotifyDep) -> list[SpotifyPlaylistOut]:
    """The signed-in user's Spotify playlists, with whether each can be imported."""
    return [SpotifyPlaylistOut(**p.__dict__) for p in await list_spotify_playlists(db, user, client)]


@router.post("/{playlist_id}/sync", response_model=ImportOut)
async def sync_playlist(
    playlist_id: PlaylistId, user: UserDep, db: DBDep, client: SpotifyDep, settings: SettingsDep
) -> ImportOut:
    """Import (or refresh) every page of a Spotify playlist into this user's cache."""
    if playlist_id.startswith("demo-"):
        raise HTTPException(status_code=400, detail="Demo playlists do not need importing")
    result = await import_playlist(db, user, client, playlist_id, settings.playlist_cache_hours)
    return ImportOut(**result.__dict__)


@router.get("/{playlist_id}/tracks", response_model=TracksPage)
def list_tracks(
    playlist: PlaylistDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> TracksPage:
    items = playlist.entries[offset : offset + limit]
    return TracksPage(
        playlist_id=playlist.id,
        total=playlist.entry_count,
        offset=offset,
        limit=limit,
        items=[EntryOut.model_validate(e.model_dump()) for e in items],
    )


@router.get("/{playlist_id}/facets", response_model=Facets)
def get_facets(playlist: PlaylistDep) -> Facets:
    artists, albums = facets(playlist)
    return Facets.model_validate({"playlist_id": playlist.id, "artists": artists, "albums": albums})


def describe_rules(spec: QuerySpec, playlist: Playlist) -> list[str]:
    artists, albums = facets(playlist)
    a_names = {str(a["id"]): str(a["name"]) for a in artists}
    al_names = {str(a["id"]): str(a["name"]) for a in albums}

    def names(ids: list[str], lookup: dict[str, str]) -> str:
        return ", ".join(dict.fromkeys(lookup.get(i, i) for i in ids))

    rules: list[str] = []
    who = "primary artist" if spec.primary_artist_only else "any credited artist"
    if spec.include_artist_ids:
        rules.append(f"Only songs where {who} is: {names(spec.include_artist_ids, a_names)}")
    if spec.include_album_ids:
        rules.append(f"Only songs from: {names(spec.include_album_ids, al_names)}")
    if spec.exclude_artist_ids:
        rules.append(f"Remove songs by: {names(spec.exclude_artist_ids, a_names)}")
    if spec.exclude_album_ids:
        rules.append(f"Remove songs from: {names(spec.exclude_album_ids, al_names)}")
    if not rules:
        rules.append("No filters: every entry in the playlist is used")
    if spec.shuffle_mode is ShuffleMode.RANDOM:
        rules.append("Order: true random (Fisher-Yates)")
    elif spec.shuffle_mode is ShuffleMode.RECENTLY_ADDED:
        band = spec.recently_added_band_days
        rules.append(
            "Order: recently added first"
            + (f", shuffled within {band}-day bands" if band else ", strictly newest first")
        )
    else:
        strict = "strict" if spec.strict_constraints else "best effort"
        rules.append(f"Order: balanced, no shared artist within {spec.minimum_artist_gap} song(s) ({strict})")
    return rules


@router.post("/{playlist_id}/preview", response_model=PreviewResponse)
def preview(playlist: PlaylistDep, spec: QuerySpec) -> PreviewResponse:
    t0 = time.perf_counter()
    filtered = apply_filters(playlist.entries, spec, explain=True)
    t1 = time.perf_counter()
    result = shuffle(
        filtered.matched,
        spec.shuffle_mode,
        seed=spec.seed,
        minimum_artist_gap=spec.minimum_artist_gap,
        strict=spec.strict_constraints,
        band_days=spec.recently_added_band_days,
    )
    t2 = time.perf_counter()
    if len(result.order) not in (0, filtered.match_count):  # defensive invariant
        raise HTTPException(status_code=500, detail="Ordering lost or duplicated entries")
    m = summarize(result.order)
    notes = list(result.notes)
    if filtered.match_count == 0:
        notes.insert(0, "No entries in this playlist match these rules.")
    queue = [
        QueueItem(
            **EntryOut.model_validate(e.model_dump()).model_dump(),
            queue_position=i,
            match_reasons=filtered.reasons.get(e.entry_id, []),
        )
        for i, e in enumerate(result.order)
    ]
    return PreviewResponse(
        playlist_id=playlist.id,
        spec=spec.model_copy(update={"seed": result.seed}),
        total_entries=filtered.total,
        match_count=filtered.match_count,
        removed_by_exclusion=filtered.removed_by_exclusion,
        mode=result.mode,
        seed=result.seed,
        status=result.status.value,
        applied_rules=describe_rules(spec, playlist),
        notes=notes,
        violations=[ViolationOut(**v.__dict__) for v in result.violations],
        metrics=OrderMetricsOut(
            adjacent_overlap_rate=m.adjacent_overlap_rate,
            same_artist_pairs_within_3=m.same_artist_pairs_within_3,
            same_artist_pairs_within_5=m.same_artist_pairs_within_5,
        ),
        timing=Timing(
            filter_ms=round((t1 - t0) * 1000, 3),
            shuffle_ms=round((t2 - t1) * 1000, 3),
            total_ms=round((time.perf_counter() - t0) * 1000, 3),
        ),
        queue=queue,
    )
