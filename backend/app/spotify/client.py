"""Async Spotify Web API client: pagination, retries, rate limits, token refresh.

Endpoints follow the Web API as checked in docs/spotify-compatibility.md
(February 2026 Development Mode changes: playlist ``/items`` paths and
``POST /me/playlists``). Network access is injected through an
``httpx.AsyncClient`` so tests can run fully offline with ``respx``.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

import httpx

API_BASE = "https://api.spotify.com/v1"
PLAYLIST_ITEMS_PAGE_LIMIT = 50  # documented maximum for GET /playlists/{id}/items
MY_PLAYLISTS_PAGE_LIMIT = 50
ADD_ITEMS_BATCH = 100  # documented maximum for POST /playlists/{id}/items


class SpotifyError(Exception):
    def __init__(self, status: int, message: str, reason: str | None = None) -> None:
        super().__init__(f"Spotify API error {status}: {message}")
        self.status = status
        self.message = message
        self.reason = reason


class SpotifyAuthError(SpotifyError):
    """The token is invalid and refreshing did not help; the user must reconnect."""


class SpotifyForbidden(SpotifyError):
    """403: not the owner/collaborator, not allowlisted, or missing scope."""


class SpotifyNotFound(SpotifyError):
    pass


class SpotifyRateLimited(SpotifyError):
    """429 that could not be absorbed by waiting (quota exceeded or too many retries)."""

    def __init__(self, message: str, retry_after: float | None, reason: str | None = None) -> None:
        super().__init__(429, message, reason)
        self.retry_after = retry_after


class TokenProvider(Protocol):
    async def access_token(self) -> str: ...

    async def refresh(self) -> str: ...


Sleep = Callable[[float], Awaitable[None]]


def _error_message(resp: httpx.Response) -> tuple[str, str | None]:
    try:
        body = resp.json()
        err = body.get("error", {})
        if isinstance(err, dict):
            return str(err.get("message", resp.reason_phrase)), err.get("reason")
        return str(body.get("error_description", err)), None
    except ValueError:
        return resp.reason_phrase, None


class SpotifyClient:
    def __init__(
        self,
        tokens: TokenProvider,
        http: httpx.AsyncClient,
        *,
        base_url: str = API_BASE,
        max_retries: int = 4,
        max_retry_after: float = 60.0,
        sleep: Sleep = asyncio.sleep,
        rng: random.Random | None = None,
    ) -> None:
        self.tokens = tokens
        self.http = http
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.max_retry_after = max_retry_after
        self.sleep = sleep
        self.rng = rng or random.Random()

    async def request(self, method: str, url: str, **kwargs: Any) -> Any:
        if not url.startswith("http"):
            url = f"{self.base_url}{url}"
        refreshed = False
        attempt = 0
        token = await self.tokens.access_token()
        while True:
            headers = {"Authorization": f"Bearer {token}", **kwargs.pop("headers", {})}
            try:
                resp = await self.http.request(method, url, headers=headers, **kwargs)
            except httpx.TransportError as exc:
                if attempt >= self.max_retries:
                    raise SpotifyError(0, f"network error: {exc}") from exc
                await self.sleep(self._backoff(attempt))
                attempt += 1
                continue

            if resp.status_code < 400:
                return resp.json() if resp.content else None

            message, reason = _error_message(resp)
            if resp.status_code == 401:
                if refreshed:
                    raise SpotifyAuthError(401, message, reason)
                token = await self.tokens.refresh()
                refreshed = True
                continue
            if resp.status_code == 429:
                retry_after = _retry_after(resp)
                if reason == "QUOTA_EXCEEDED":
                    raise SpotifyRateLimited(message, retry_after, reason)
                if attempt >= self.max_retries or (
                    retry_after is not None and retry_after > self.max_retry_after
                ):
                    raise SpotifyRateLimited(message, retry_after, reason)
                await self.sleep(retry_after if retry_after is not None else self._backoff(attempt))
                attempt += 1
                continue
            if resp.status_code >= 500:
                if attempt >= self.max_retries:
                    raise SpotifyError(resp.status_code, message, reason)
                await self.sleep(self._backoff(attempt))
                attempt += 1
                continue
            if resp.status_code == 403:
                raise SpotifyForbidden(403, message, reason)
            if resp.status_code == 404:
                raise SpotifyNotFound(404, message, reason)
            raise SpotifyError(resp.status_code, message, reason)

    def _backoff(self, attempt: int) -> float:
        return float(min(30.0, 0.5 * 2.0**attempt) * (0.5 + self.rng.random() / 2))

    async def paginate(self, url: str, params: dict[str, Any] | None = None) -> AsyncIterator[Any]:
        """Follow ``next`` links until the last page."""
        page = await self.request("GET", url, params=params)
        while True:
            for item in page.get("items", []):
                yield item
            nxt = page.get("next")
            if not nxt:
                return
            page = await self.request("GET", nxt)

    # endpoints ------------------------------------------------------------
    async def me(self) -> dict[str, Any]:
        result: dict[str, Any] = await self.request("GET", "/me")
        return result

    async def my_playlists(self) -> list[dict[str, Any]]:
        return [p async for p in self.paginate("/me/playlists", {"limit": MY_PLAYLISTS_PAGE_LIMIT})]

    async def playlist(self, playlist_id: str) -> dict[str, Any]:
        result: dict[str, Any] = await self.request("GET", f"/playlists/{playlist_id}")
        return result

    async def playlist_items(self, playlist_id: str) -> list[dict[str, Any]]:
        params = {"limit": PLAYLIST_ITEMS_PAGE_LIMIT, "additional_types": "track"}
        return [i async for i in self.paginate(f"/playlists/{playlist_id}/items", params)]

    async def create_playlist(self, name: str, description: str = "", public: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = await self.request(
            "POST",
            "/me/playlists",
            json={"name": name, "description": description, "public": public},
        )
        return result

    async def add_items(self, playlist_id: str, uris: list[str]) -> dict[str, Any]:
        if not 0 < len(uris) <= ADD_ITEMS_BATCH:
            raise ValueError(f"add_items takes 1..{ADD_ITEMS_BATCH} URIs, got {len(uris)}")
        result: dict[str, Any] = await self.request(
            "POST", f"/playlists/{playlist_id}/items", json={"uris": uris}
        )
        return result


def _retry_after(resp: httpx.Response) -> float | None:
    value = resp.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
