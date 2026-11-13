"""Database tables for live Spotify mode.

Retention is deliberately minimal (Spotify Developer Terms IV.3): a playlist is
cached as one JSON document per user with an expiry, rather than building a
permanent catalogue of tracks, artists and albums. Deleting a user cascades to
everything that belongs to them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    spotify_user_id: Mapped[str] = mapped_column(String(128), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    connection: Mapped[SpotifyConnection | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class SpotifyConnection(Base):
    """OAuth tokens, encrypted with a key derived from the session secret."""

    __tablename__ = "spotify_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    access_token_enc: Mapped[str] = mapped_column(Text)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[str] = mapped_column(String(500), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="connection")


class Session(Base):
    """Browser sessions. Only a SHA-256 hash of the cookie value is stored."""

    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlaylistCache(Base):
    __tablename__ = "playlist_caches"
    __table_args__ = (UniqueConstraint("user_id", "spotify_playlist_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    spotify_playlist_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    snapshot_id: Mapped[str | None] = mapped_column(String(200))
    entry_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_unavailable: Mapped[int] = mapped_column(Integer, default=0)
    skipped_episodes: Mapped[int] = mapped_column(Integer, default=0)
    entries_json: Mapped[str] = mapped_column(Text)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExportJob(Base):
    __tablename__ = "export_jobs"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    source_playlist_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(300), default="")
    uris_json: Mapped[str] = mapped_column(Text)  # the exact order to write
    total_items: Mapped[int] = mapped_column(Integer)
    skipped_items: Mapped[int] = mapped_column(Integer, default=0)
    completed_items: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    destination_playlist_id: Mapped[str | None] = mapped_column(String(64))
    destination_url: Mapped[str | None] = mapped_column(String(300))
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    batches: Mapped[list[ExportJobBatch]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="ExportJobBatch.index"
    )


class ExportJobBatch(Base):
    """One add-items request (up to 100 songs) and its outcome."""

    __tablename__ = "export_job_batches"
    __table_args__ = (UniqueConstraint("job_id", "index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("export_jobs.id", ondelete="CASCADE"))
    index: Mapped[int] = mapped_column(Integer)
    size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    snapshot_id: Mapped[str | None] = mapped_column(String(200))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
