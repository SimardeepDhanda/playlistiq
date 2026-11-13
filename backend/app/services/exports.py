"""Export an ordered preview to a NEW Spotify playlist, safely and resumably.

Safety rules:

* The source playlist is never modified; export always creates a new playlist.
* A job is identified by (user, Idempotency-Key). Repeating the request returns
  the same job instead of creating a second playlist.
* The destination playlist ID is saved the moment it is created, so a retry
  reuses it rather than creating a duplicate.
* Adding items is not idempotent on Spotify's side, so before resuming, the job
  reads how many items the destination already holds and continues from there.
* At the end every item is read back and compared with the intended order.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DB

from app.db.models import ExportJob, ExportJobBatch, User
from app.engine.filters import apply_filters
from app.engine.models import QuerySpec
from app.engine.shuffle import ShuffleStatus, shuffle
from app.services.demo import Playlist
from app.spotify.client import ADD_ITEMS_BATCH, SpotifyClient, SpotifyError

EXPORTABLE_PREFIX = "spotify:track:"


class ExportRejected(ValueError):
    pass


def ordered_uris(playlist: Playlist, spec: QuerySpec) -> tuple[list[str], int, int]:
    """The exact order the preview showed, as URIs. Returns (uris, skipped, seed).

    Local files and items without a Spotify track URI cannot be added to a
    playlist through the API, so they are skipped and counted.
    """
    if spec.seed is None:
        raise ExportRejected("Export needs the seed from the preview so the order is identical.")
    matched = apply_filters(playlist.entries, spec).matched
    result = shuffle(
        matched,
        spec.shuffle_mode,
        seed=spec.seed,
        minimum_artist_gap=spec.minimum_artist_gap,
        strict=spec.strict_constraints,
        band_days=spec.recently_added_band_days,
    )
    if result.status in (ShuffleStatus.INFEASIBLE, ShuffleStatus.NOT_FOUND):
        raise ExportRejected("These rules do not produce an order, so there is nothing to export.")
    uris = [e.uri for e in result.order if e.uri and e.uri.startswith(EXPORTABLE_PREFIX) and not e.is_local]
    return uris, len(result.order) - len(uris), spec.seed


def get_or_create_job(
    db: DB, user: User, key: str, playlist: Playlist, spec: QuerySpec, name: str, description: str
) -> tuple[ExportJob, bool]:
    existing = db.scalar(
        select(ExportJob).where(ExportJob.user_id == user.id, ExportJob.idempotency_key == key)
    )
    if existing is not None:
        if existing.source_playlist_id != playlist.id:
            raise ExportRejected("This idempotency key was already used for a different export.")
        return existing, False
    if playlist.source != "spotify":
        raise ExportRejected("Demo playlists contain synthetic songs and cannot be exported.")
    uris, skipped, _ = ordered_uris(playlist, spec)
    if not uris:
        raise ExportRejected("No songs in this selection can be added to a Spotify playlist.")
    job = ExportJob(
        user_id=user.id,
        idempotency_key=key,
        source_playlist_id=playlist.id,
        name=name,
        description=description,
        uris_json=json.dumps(uris),
        total_items=len(uris),
        skipped_items=skipped,
    )
    db.add(job)
    db.commit()
    return job, True


def _touch(db: DB, job: ExportJob, **fields: Any) -> None:
    for k, v in fields.items():
        setattr(job, k, v)
    job.updated_at = datetime.now(UTC)
    db.commit()


async def _destination_uris(client: SpotifyClient, playlist_id: str) -> list[str]:
    items = await client.playlist_items(playlist_id)
    out = []
    for raw in items:
        obj = raw.get("item") or raw.get("track") or {}
        out.append(obj.get("uri") or "")
    return out


async def run_export(db: DB, job: ExportJob, client: SpotifyClient) -> ExportJob:
    if job.status == "completed":
        return job
    uris: list[str] = json.loads(job.uris_json)
    _touch(db, job, status="running", error=None, attempts=job.attempts + 1)
    try:
        if not job.destination_playlist_id:
            created = await client.create_playlist(job.name, job.description, public=False)
            _touch(
                db,
                job,
                destination_playlist_id=created["id"],
                destination_url=(created.get("external_urls") or {}).get("spotify")
                or f"https://open.spotify.com/playlist/{created['id']}",
            )
        else:
            # Resume: trust what the destination actually holds, if it is a prefix of
            # the intended order. Anything else needs a human, not a blind retry.
            present = await _destination_uris(client, job.destination_playlist_id)
            if present != uris[: len(present)]:
                raise ExportRejected(
                    "The new playlist was changed outside PlaylistIQ, so the export stopped "
                    "instead of guessing. Delete it in Spotify and export again."
                )
            _touch(db, job, completed_items=len(present))

        assert job.destination_playlist_id is not None
        while job.completed_items < len(uris):
            start = job.completed_items
            chunk = uris[start : start + ADD_ITEMS_BATCH]
            resp = await client.add_items(job.destination_playlist_id, chunk)
            db.add(
                ExportJobBatch(
                    job_id=job.id,
                    index=start // ADD_ITEMS_BATCH,
                    size=len(chunk),
                    status="added",
                    snapshot_id=(resp or {}).get("snapshot_id"),
                )
            )
            _touch(db, job, completed_items=start + len(chunk))

        final = await _destination_uris(client, job.destination_playlist_id)
        if final != uris:
            raise ExportRejected(
                f"Verification failed: the new playlist has {len(final)} items, expected "
                f"{len(uris)} in order."
            )
        _touch(db, job, status="completed")
    except (SpotifyError, ExportRejected) as exc:
        message = exc.message if isinstance(exc, SpotifyError) else str(exc)
        _touch(db, job, status="failed", error=message)
    return job
