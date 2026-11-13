from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import playlists, query
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="PlaylistIQ API",
        version="0.1.0",
        description="Playlist-scoped filtering and configurable ordering.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Idempotency-Key"],
    )

    @app.get("/health", tags=["health"])
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "demo_mode": True,
            "spotify_configured": settings.spotify_enabled,
        }

    app.include_router(playlists.router)
    app.include_router(query.router)
    return app


app = create_app()
