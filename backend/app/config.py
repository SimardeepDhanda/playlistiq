"""Runtime settings, read from environment variables (see .env.example)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PLAYLISTIQ_", extra="ignore")

    environment: str = "development"
    demo_data_path: Path = REPO_ROOT / "sample_data" / "demo_playlists.json"
    cors_origins: list[str] = ["http://127.0.0.1:3000", "http://localhost:3000"]

    # Spotify. Live mode stays disabled until a client ID is configured.
    spotify_client_id: str | None = None
    spotify_redirect_uri: str = "http://127.0.0.1:8000/api/auth/spotify/callback"
    frontend_url: str = "http://127.0.0.1:3000"
    session_secret: str | None = None
    # Reserved for live mode (cached playlists, export jobs). Demo mode does not use a database.
    database_url: str | None = None

    @property
    def spotify_enabled(self) -> bool:
        return bool(self.spotify_client_id)


@lru_cache
def get_settings() -> Settings:
    return Settings()
