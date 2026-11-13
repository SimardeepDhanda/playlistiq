from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from app.auth import pkce
from app.spotify.client import (
    API_BASE,
    SpotifyAuthError,
    SpotifyClient,
    SpotifyForbidden,
    SpotifyRateLimited,
)
from app.spotify.normalize import normalize_items


class FakeTokens:
    def __init__(self) -> None:
        self.token = "access-1"
        self.refreshes = 0

    async def access_token(self) -> str:
        return self.token

    async def refresh(self) -> str:
        self.refreshes += 1
        self.token = f"access-{self.refreshes + 1}"
        return self.token


class SleepRecorder:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def _item(i: int) -> dict[str, Any]:
    return {
        "added_at": "2025-01-01T00:00:00Z",
        "is_local": False,
        "item": {
            "type": "track",
            "id": f"t{i}",
            "uri": f"spotify:track:t{i}",
            "name": f"Song {i}",
            "artists": [{"id": "a1", "name": "Artist"}],
            "album": {"id": "al1", "name": "Album", "album_type": "album", "artists": []},
            "duration_ms": 1000,
        },
    }


@pytest.fixture
def sleep() -> SleepRecorder:
    return SleepRecorder()


@pytest.fixture
async def client(sleep: SleepRecorder) -> Any:
    async with httpx.AsyncClient() as http:
        yield SpotifyClient(FakeTokens(), http, sleep=sleep)


@respx.mock
async def test_pagination_fetches_all_2000_items(client: SpotifyClient) -> None:
    total, limit = 2000, 50

    def page(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", 0))
        items = [_item(i) for i in range(offset, min(offset + limit, total))]
        nxt = (
            f"{API_BASE}/playlists/pl/items?offset={offset + limit}&limit={limit}"
            if offset + limit < total
            else None
        )
        return httpx.Response(200, json={"items": items, "next": nxt, "total": total})

    route = respx.get(f"{API_BASE}/playlists/pl/items").mock(side_effect=page)
    items = await client.playlist_items("pl")
    assert len(items) == total
    assert route.call_count == total // limit
    assert [i["item"]["id"] for i in items] == [f"t{i}" for i in range(total)]
    assert route.calls[0].request.url.params["limit"] == "50"


@respx.mock
async def test_429_waits_for_retry_after(client: SpotifyClient, sleep: SleepRecorder) -> None:
    route = respx.get(f"{API_BASE}/me").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "3"}, json={"error": {"status": 429}}),
            httpx.Response(200, json={"id": "me"}),
        ]
    )
    assert await client.me() == {"id": "me"}
    assert sleep.calls == [3.0]
    assert route.call_count == 2


@respx.mock
async def test_429_with_huge_retry_after_is_surfaced(client: SpotifyClient) -> None:
    respx.get(f"{API_BASE}/me").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "3600"}, json={})
    )
    with pytest.raises(SpotifyRateLimited) as exc:
        await client.me()
    assert exc.value.retry_after == 3600


@respx.mock
async def test_quota_exceeded_is_not_retried(client: SpotifyClient, sleep: SleepRecorder) -> None:
    respx.get(f"{API_BASE}/me").mock(
        return_value=httpx.Response(
            429, json={"error": {"status": 429, "message": "quota", "reason": "QUOTA_EXCEEDED"}}
        )
    )
    with pytest.raises(SpotifyRateLimited) as exc:
        await client.me()
    assert exc.value.reason == "QUOTA_EXCEEDED"
    assert sleep.calls == []


@respx.mock
async def test_expired_token_refreshes_once(client: SpotifyClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers["Authorization"] == "Bearer access-1":
            return httpx.Response(401, json={"error": {"status": 401, "message": "expired"}})
        return httpx.Response(200, json={"id": "me"})

    respx.get(f"{API_BASE}/me").mock(side_effect=handler)
    assert await client.me() == {"id": "me"}
    assert client.tokens.refreshes == 1  # type: ignore[attr-defined]


@respx.mock
async def test_repeated_401_raises_auth_error(client: SpotifyClient) -> None:
    respx.get(f"{API_BASE}/me").mock(return_value=httpx.Response(401, json={}))
    with pytest.raises(SpotifyAuthError):
        await client.me()
    assert client.tokens.refreshes == 1  # type: ignore[attr-defined]


@respx.mock
async def test_5xx_backs_off_then_succeeds(client: SpotifyClient, sleep: SleepRecorder) -> None:
    respx.get(f"{API_BASE}/me").mock(
        side_effect=[httpx.Response(502), httpx.Response(503), httpx.Response(200, json={"id": "me"})]
    )
    assert await client.me() == {"id": "me"}
    assert len(sleep.calls) == 2
    assert sleep.calls[1] > 0


@respx.mock
async def test_403_not_owner_is_forbidden(client: SpotifyClient) -> None:
    respx.get(f"{API_BASE}/playlists/x/items").mock(
        return_value=httpx.Response(403, json={"error": {"status": 403, "message": "Forbidden"}})
    )
    with pytest.raises(SpotifyForbidden):
        await client.playlist_items("x")


@respx.mock
async def test_create_playlist_and_add_items_use_current_endpoints(client: SpotifyClient) -> None:
    create = respx.post(f"{API_BASE}/me/playlists").mock(return_value=httpx.Response(201, json={"id": "new"}))
    add = respx.post(f"{API_BASE}/playlists/new/items").mock(
        return_value=httpx.Response(201, json={"snapshot_id": "s1"})
    )
    await client.create_playlist("Mix", "desc")
    await client.add_items("new", [f"spotify:track:{i}" for i in range(100)])
    assert create.called and add.called
    with pytest.raises(ValueError):
        await client.add_items("new", ["x"] * 101)


def test_normalize_handles_messy_items() -> None:
    items = [
        _item(0),
        {"added_at": None, "item": None},  # removed or unavailable
        {"added_at": "2025-01-01T00:00:00Z", "item": {"type": "episode", "id": "e"}},
        {  # deprecated "track" key, local file with no IDs
            "added_at": "2025-01-02T00:00:00Z",
            "is_local": True,
            "track": {
                "type": "track",
                "id": None,
                "uri": "spotify:local:x",
                "name": "Demo",
                "artists": [{"id": None, "name": "Garage Band"}],
                "album": None,
            },
        },
        _item(0),  # duplicate occurrence of the same track
    ]
    report = normalize_items("pl", items)
    assert report.skipped_unavailable == 1
    assert report.skipped_episodes == 1
    assert [e.entry_id for e in report.entries] == ["pl:0", "pl:3", "pl:4"]
    local = report.entries[1]
    assert local.is_local and local.track_id is None and local.album is None
    assert local.artists[0].key == "local-artist:garage band"
    assert report.entries[0].track_id == report.entries[2].track_id == "t0"


def test_pkce_rfc7636_example() -> None:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert pkce.code_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_pkce_verifier_and_url() -> None:
    v = pkce.code_verifier()
    assert 43 <= len(v) <= 128
    url = pkce.authorize_url("cid", "http://127.0.0.1:8000/cb", "st", v)
    assert "code_challenge_method=S256" in url and "state=st" in url
    assert "playlist-modify-public" not in url
    assert pkce.states_match("abc", "abc")
    assert not pkce.states_match("abc", "abd")
    assert not pkce.states_match(None, None)
