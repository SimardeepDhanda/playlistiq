"""Runtime settings, read from environment variables (see .env.example)."""

from __future__ import annotations

import secrets
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
    # Live mode keeps sessions, encrypted tokens, playlist caches and export jobs here.
    # SQLite needs no setup; set a postgresql+psycopg:// URL to use Postgres instead.
    database_url: str = f"sqlite:///{REPO_ROOT / 'backend' / 'playlistiq.db'}"
    playlist_cache_hours: int = 24
    session_days: int = 14

    @property
    def spotify_enabled(self) -> bool:
        return bool(self.spotify_client_id)

    @property
    def secure_cookies(self) -> bool:
        return self.frontend_url.startswith("https://")

    def secret(self) -> str:
        """Key material for signing cookies and encrypting tokens.

        Production must set PLAYLISTIQ_SESSION_SECRET. For local development a
        random secret is created once in backend/.local_secret (git-ignored).
        """
        if self.session_secret:
            return self.session_secret
        if self.environment == "production":
            raise RuntimeError("PLAYLISTIQ_SESSION_SECRET must be set in production")
        path = REPO_ROOT / "backend" / ".local_secret"
        if not path.exists():
            path.write_text(secrets.token_urlsafe(48))
            path.chmod(0o600)
        return path.read_text().strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()
