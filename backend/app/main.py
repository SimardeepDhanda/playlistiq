from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, exports, playlists, query
from app.config import get_settings
from app.db.session import migrate
from app.spotify.client import (
    SpotifyAuthError,
    SpotifyError,
    SpotifyForbidden,
    SpotifyNotFound,
    SpotifyRateLimited,
)

CSRF_HEADER = "X-PlaylistIQ"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        migrate(settings.database_url)
        yield

    app = FastAPI(
        title="PlaylistIQ API",
        version="0.2.0",
        description="Playlist-scoped filtering and configurable ordering.",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def csrf_guard(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        # Cookie-authenticated writes must carry a custom header. Browsers cannot add
        # one cross-site without a CORS preflight, which only allowed origins pass.
        if (
            request.method in UNSAFE
            and request.url.path.startswith("/api/")
            and request.headers.get(CSRF_HEADER) != "1"
        ):
            return JSONResponse({"detail": "Missing X-PlaylistIQ header"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(SpotifyError)
    async def spotify_error(_: Request, exc: SpotifyError) -> JSONResponse:
        if isinstance(exc, SpotifyAuthError):
            return JSONResponse({"detail": "Spotify session expired. Please reconnect."}, 401)
        if isinstance(exc, SpotifyForbidden):
            return JSONResponse({"detail": exc.message}, 403)
        if isinstance(exc, SpotifyNotFound):
            return JSONResponse({"detail": "Not found on Spotify"}, 404)
        if isinstance(exc, SpotifyRateLimited):
            headers = {"Retry-After": str(int(exc.retry_after))} if exc.retry_after else {}
            detail = (
                "This app has used its Spotify request quota. Try again later."
                if exc.reason == "QUOTA_EXCEEDED"
                else "Spotify is rate limiting requests. Try again shortly."
            )
            return JSONResponse({"detail": detail}, 429, headers=headers)
        return JSONResponse({"detail": "Spotify returned an error. Try again."}, 502)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Idempotency-Key", CSRF_HEADER],
    )

    @app.get("/health", tags=["health"])
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "demo_mode": not settings.spotify_enabled,
            "spotify_configured": settings.spotify_enabled,
        }

    app.include_router(auth.router)
    app.include_router(playlists.router)
    app.include_router(query.router)
    app.include_router(exports.router)
    return app


app = create_app()
