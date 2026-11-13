from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import sessionmaker

from app.api.deps import CipherDep, DBDep, SettingsDep, SourceDep, UserDep
from app.auth.security import TokenCipher
from app.auth.sessions import DBTokenProvider
from app.config import Settings
from app.db.models import ExportJob, User
from app.db.session import engine_for
from app.engine.models import QuerySpec
from app.services.exports import ExportRejected, get_or_create_job, run_export
from app.services.playlists import PlaylistNotFound, PlaylistNotImported
from app.spotify.client import SpotifyClient

router = APIRouter(prefix="/api/exports", tags=["exports"])

IdempotencyKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
]


class ExportRequest(BaseModel):
    playlist_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    spec: QuerySpec
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=300)


class ExportStatus(BaseModel):
    id: str
    status: str
    source_playlist_id: str
    name: str
    total_items: int
    completed_items: int
    skipped_items: int
    batches_done: int
    destination_playlist_id: str | None
    destination_url: str | None
    error: str | None
    attempts: int


def _status(job: ExportJob) -> ExportStatus:
    return ExportStatus(
        id=job.id,
        status=job.status,
        source_playlist_id=job.source_playlist_id,
        name=job.name,
        total_items=job.total_items,
        completed_items=job.completed_items,
        skipped_items=job.skipped_items,
        batches_done=len(job.batches),
        destination_playlist_id=job.destination_playlist_id,
        destination_url=job.destination_url,
        error=job.error,
        attempts=job.attempts,
    )


async def _run_in_background(job_id: str, user_id: str, settings: Settings, cipher: TokenCipher) -> None:
    """Runs after the response with its own DB session and HTTP client."""
    import httpx

    factory = sessionmaker(engine_for(settings.database_url), expire_on_commit=False)
    with factory() as db:
        job = db.get(ExportJob, job_id)
        user = db.get(User, user_id)
        if job is None or user is None:
            return
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as http:
            client = SpotifyClient(DBTokenProvider(db, user, cipher, settings, http), http)
            await run_export(db, job, client)


def _owned_job(db: DBDep, user: User, job_id: str) -> ExportJob:
    job = db.get(ExportJob, job_id)
    if job is None or job.user_id != user.id:  # never reveal other users' jobs
        raise HTTPException(status_code=404, detail="Export not found")
    return job


@router.post("", response_model=ExportStatus, status_code=202)
async def start_export(
    body: ExportRequest,
    key: IdempotencyKey,
    user: UserDep,
    db: DBDep,
    source: SourceDep,
    settings: SettingsDep,
    cipher: CipherDep,
    background: BackgroundTasks,
) -> ExportStatus:
    try:
        playlist = await source.get(body.playlist_id)
    except PlaylistNotImported:
        raise HTTPException(status_code=409, detail="Import this playlist first") from None
    except PlaylistNotFound:
        raise HTTPException(status_code=404, detail="Playlist not found") from None
    try:
        job, _created = get_or_create_job(db, user, key, playlist, body.spec, body.name, body.description)
    except ExportRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if job.status in ("pending", "failed"):
        background.add_task(_run_in_background, job.id, user.id, settings, cipher)
    return _status(job)


@router.get("/{job_id}", response_model=ExportStatus)
def get_export(job_id: str, user: UserDep, db: DBDep) -> ExportStatus:
    return _status(_owned_job(db, user, job_id))


@router.post("/{job_id}/retry", response_model=ExportStatus, status_code=202)
def retry_export(
    job_id: str,
    user: UserDep,
    db: DBDep,
    settings: SettingsDep,
    cipher: CipherDep,
    background: BackgroundTasks,
) -> ExportStatus:
    job = _owned_job(db, user, job_id)
    if job.status != "failed":
        raise HTTPException(status_code=409, detail=f"Export is {job.status}, not failed")
    background.add_task(_run_in_background, job.id, user.id, settings, cipher)
    return _status(job)
