"""Live Spotify mode against a simulated Spotify (respx). No network access."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth.pkce import TOKEN_URL, code_challenge
from app.config import Settings, get_settings
from app.db.models import ExportJob, PlaylistCache, Session, SpotifyConnection, User
from app.db.session import engine_for
from app.main import app
from app.spotify.client import API_BASE

OWNED = "ownedPlaylist000000001"
FOREIGN = "foreignPlaylist0000001"


def live_settings() -> Settings:
    base = get_settings()
    return base.model_copy(update={"spotify_client_id": "test-client-id"})


class FakeSpotify:
    """Just enough of Spotify's accounts service and Web API, with state."""

    def __init__(self, router: respx.MockRouter, n_items: int = 230) -> None:
        self.created: list[str] = []
        self.added: dict[str, list[str]] = {}
        self.add_calls = 0
        self.fail_add_on_call: set[int] = set()
        self.refreshes = 0
        self.last_token_form: dict[str, str] = {}
        self.items = [self._item(i) for i in range(n_items)]
        router.post(TOKEN_URL).mock(side_effect=self.token)
        router.get(f"{API_BASE}/me").mock(side_effect=self.me)
        router.get(f"{API_BASE}/me/playlists").mock(side_effect=self.my_playlists)
        router.post(f"{API_BASE}/me/playlists").mock(side_effect=self.create)
        router.get(url__regex=rf"{re.escape(API_BASE)}/playlists/[^/]+/items.*").mock(
            side_effect=self.get_items
        )
        router.post(url__regex=rf"{re.escape(API_BASE)}/playlists/[^/]+/items").mock(
            side_effect=self.add_items
        )
        router.get(url__regex=rf"{re.escape(API_BASE)}/playlists/[^/?]+(\?.*)?$").mock(
            side_effect=self.playlist
        )

    @staticmethod
    def _item(i: int) -> dict[str, Any]:
        artist = {"id": f"art{i % 7}", "name": f"Artist {i % 7}"}
        return {
            "added_at": "2025-01-01T00:00:00Z",
            "is_local": False,
            "item": {
                "type": "track",
                "id": f"trk{i}",
                "uri": f"spotify:track:trk{i}",
                "name": f"Song {i}",
                "artists": [artist],
                "album": {"id": f"alb{i % 5}", "name": f"Album {i % 5}", "artists": [artist]},
                "duration_ms": 200000,
            },
        }

    @staticmethod
    def _user(request: httpx.Request) -> str:
        return request.headers["Authorization"].split("-", 1)[1]  # "Bearer at-<user>"

    def token(self, request: httpx.Request) -> httpx.Response:
        form = parse_qs(request.content.decode())
        self.last_token_form = {k: v[0] for k, v in form.items()}
        if form["grant_type"][0] == "authorization_code":
            user = form["code"][0].removeprefix("code-")
            assert form["code_verifier"][0]
        else:
            self.refreshes += 1
            user = form["refresh_token"][0].removeprefix("rt-")
        return httpx.Response(
            200,
            json={
                "access_token": f"at-{user}",
                "refresh_token": f"rt-{user}",
                "expires_in": 3600,
                "scope": "playlist-read-private playlist-modify-private",
            },
        )

    def me(self, request: httpx.Request) -> httpx.Response:
        user = self._user(request)
        return httpx.Response(200, json={"id": user, "display_name": user.title()})

    def my_playlists(self, request: httpx.Request) -> httpx.Response:
        user = self._user(request)
        return httpx.Response(
            200,
            json={
                "next": None,
                "items": [
                    {
                        "id": OWNED,
                        "name": "Mine",
                        "owner": {"id": user},
                        "collaborative": False,
                        "items": {"total": len(self.items)},
                    },
                    {
                        "id": FOREIGN,
                        "name": "Editorial",
                        "owner": {"id": "spotify"},
                        "collaborative": False,
                        "items": {"total": 50},
                    },
                ],
            },
        )

    def playlist(self, request: httpx.Request) -> httpx.Response:
        pid = request.url.path.rsplit("/", 1)[1]
        owner = "spotify" if pid == FOREIGN else self._user(request)
        return httpx.Response(
            200,
            json={
                "id": pid,
                "name": "Mine" if pid == OWNED else pid,
                "description": "",
                "owner": {"id": owner},
                "collaborative": False,
                "snapshot_id": "s1",
            },
        )

    def get_items(self, request: httpx.Request) -> httpx.Response:
        pid = request.url.path.split("/")[-2]
        if pid == FOREIGN:
            return httpx.Response(403, json={"error": {"status": 403, "message": "Forbidden"}})
        source = (
            self.items
            if pid == OWNED
            else [{"added_at": None, "item": {"type": "track", "uri": u}} for u in self.added.get(pid, [])]
        )
        offset = int(request.url.params.get("offset", 0))
        limit = int(request.url.params.get("limit", 50))
        nxt = None
        if offset + limit < len(source):
            nxt = f"{API_BASE}/playlists/{pid}/items?offset={offset + limit}&limit={limit}"
        return httpx.Response(
            200, json={"items": source[offset : offset + limit], "next": nxt, "total": len(source)}
        )

    def create(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["public"] is False
        pid = f"dest{len(self.created):018d}"
        self.created.append(pid)
        self.added[pid] = []
        return httpx.Response(
            201, json={"id": pid, "external_urls": {"spotify": f"https://open.spotify.com/playlist/{pid}"}}
        )

    def add_items(self, request: httpx.Request) -> httpx.Response:
        self.add_calls += 1
        if self.add_calls in self.fail_add_on_call:
            return httpx.Response(500, json={"error": {"status": 500, "message": "boom"}})
        pid = request.url.path.split("/")[-2]
        uris = json.loads(request.content)["uris"]
        assert len(uris) <= 100
        self.added[pid].extend(uris)
        return httpx.Response(201, json={"snapshot_id": f"snap{self.add_calls}"})


@pytest.fixture
def spotify() -> Iterator[FakeSpotify]:
    app.dependency_overrides[get_settings] = live_settings
    with respx.mock(assert_all_called=False) as router:
        router.route(host="testserver").pass_through()
        yield FakeSpotify(router)
    app.dependency_overrides.clear()


def login(user: str) -> TestClient:
    c = TestClient(app, headers={"X-PlaylistIQ": "1"}, follow_redirects=False)
    c.__enter__()
    start = c.get("/api/auth/spotify/start")
    assert start.status_code == 307
    params = parse_qs(urlparse(start.headers["location"]).query)
    cb = c.get("/api/auth/spotify/callback", params={"code": f"code-{user}", "state": params["state"][0]})
    assert cb.status_code == 303, cb.text
    assert cb.headers["location"].endswith("/dashboard")
    return c


def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_: float) -> None:
        return None

    monkeypatch.setattr("app.spotify.client.asyncio.sleep", instant)


def db_count(model: Any, **where: Any) -> int:
    from sqlalchemy.orm import Session as DB

    with DB(engine_for(get_settings().database_url)) as db:
        q = select(func.count()).select_from(model)
        for k, v in where.items():
            q = q.where(getattr(model, k) == v)
        return int(db.scalar(q) or 0)


# ------------------------------------------------------------------ sign-in


def test_start_uses_pkce_and_least_privilege_scopes(spotify: FakeSpotify) -> None:
    with TestClient(app, follow_redirects=False) as c:
        r = c.get("/api/auth/spotify/start")
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["code_challenge_method"] == ["S256"]
    assert q["redirect_uri"] == ["http://127.0.0.1:8000/api/auth/spotify/callback"]
    assert set(q["scope"][0].split()) == {
        "playlist-read-private",
        "playlist-read-collaborative",
        "playlist-modify-private",
    }
    assert "piq_oauth" in r.cookies


def test_start_without_client_id_is_503() -> None:
    with TestClient(app) as c:
        assert c.get("/api/auth/spotify/start").status_code == 503


def test_callback_rejects_wrong_state(spotify: FakeSpotify) -> None:
    with TestClient(app, follow_redirects=False) as c:
        c.get("/api/auth/spotify/start")
        r = c.get("/api/auth/spotify/callback", params={"code": "code-x", "state": "forged"})
    assert r.status_code == 303 and "auth_error=state_mismatch" in r.headers["location"]
    assert "piq_session" not in r.cookies


def test_callback_without_start_cookie_is_rejected(spotify: FakeSpotify) -> None:
    with TestClient(app, follow_redirects=False) as c:
        r = c.get("/api/auth/spotify/callback", params={"code": "code-x", "state": "s"})
    assert "auth_error=state_mismatch" in r.headers["location"]


def test_login_stores_encrypted_tokens_and_hashed_session(spotify: FakeSpotify) -> None:
    c = login("alice")
    assert c.get("/api/auth/me").json()["connected"] is True
    from sqlalchemy.orm import Session as DB

    with DB(engine_for(get_settings().database_url)) as db:
        user = db.scalar(select(User).where(User.spotify_user_id == "alice"))
        assert user is not None
        conn = db.scalar(select(SpotifyConnection).where(SpotifyConnection.user_id == user.id))
        assert conn is not None and "at-alice" not in conn.access_token_enc
        assert c.cookies["piq_session"] not in {s.token_hash for s in db.scalars(select(Session))}


def test_expired_token_is_refreshed(spotify: FakeSpotify) -> None:
    c = login("bob")
    from sqlalchemy.orm import Session as DB

    with DB(engine_for(get_settings().database_url)) as db:
        user = db.scalar(select(User).where(User.spotify_user_id == "bob"))
        assert user is not None
        conn = db.scalar(select(SpotifyConnection).where(SpotifyConnection.user_id == user.id))
        assert conn is not None
        conn.expires_at = datetime.now(UTC) - timedelta(minutes=5)
        db.commit()
    assert c.get("/api/playlists/spotify").status_code == 200
    assert spotify.refreshes == 1


def test_logout(spotify: FakeSpotify) -> None:
    c = login("carol")
    assert c.post("/api/auth/logout").status_code == 204
    assert c.get("/api/auth/me").json()["connected"] is False


# ---------------------------------------------------------- playlists


def test_list_marks_unreadable_playlists(spotify: FakeSpotify) -> None:
    c = login("dave")
    rows = {p["id"]: p for p in c.get("/api/playlists/spotify").json()}
    assert rows[OWNED]["readable"] is True and rows[OWNED]["imported"] is False
    assert rows[FOREIGN]["readable"] is False


def test_import_fetches_every_page_then_previews(spotify: FakeSpotify) -> None:
    c = login("erin")
    r = c.post(f"/api/playlists/{OWNED}/sync")
    assert r.status_code == 200 and r.json()["entry_count"] == 230
    assert c.get("/api/playlists/spotify").json()[0]["imported"] is True
    p = c.post(f"/api/playlists/{OWNED}/preview", json={"seed": 1, "minimum_artist_gap": 2})
    assert p.status_code == 200
    assert p.json()["match_count"] == 230 and p.json()["status"] == "ok"


def test_importing_someone_elses_playlist_is_refused(spotify: FakeSpotify) -> None:
    c = login("frank")
    r = c.post(f"/api/playlists/{FOREIGN}/sync")
    assert r.status_code == 403
    assert "own or collaborate" in r.json()["detail"]


def test_users_cannot_see_each_others_cache_or_exports(spotify: FakeSpotify) -> None:
    a = login("grace")
    a.post(f"/api/playlists/{OWNED}/sync")
    job = a.post(
        "/api/exports",
        headers={"Idempotency-Key": "grace-key-0001"},
        json={"playlist_id": OWNED, "spec": {"seed": 3}, "name": "Mix"},
    ).json()

    b = login("heidi")
    assert b.get(f"/api/playlists/{OWNED}/tracks").status_code == 409  # B has not imported it
    assert b.post(f"/api/playlists/{OWNED}/preview", json={}).status_code == 409
    assert b.get(f"/api/exports/{job['id']}").status_code == 404
    with TestClient(app) as anonymous:
        assert anonymous.get(f"/api/playlists/{OWNED}/tracks").status_code == 404
        assert anonymous.get(f"/api/exports/{job['id']}").status_code == 401


def test_live_parse_query_uses_imported_metadata(spotify: FakeSpotify) -> None:
    c = login("ivan")
    c.post(f"/api/playlists/{OWNED}/sync")
    r = c.post("/api/parse-query", json={"playlist_id": OWNED, "text": "only Artist 3"})
    assert r.json()["spec"]["include_artist_ids"] == ["art3"]


# ------------------------------------------------------------------ export


def _export(c: TestClient, key: str, spec: dict[str, Any] | None = None) -> httpx.Response:
    return c.post(
        "/api/exports",
        headers={"Idempotency-Key": key},
        json={
            "playlist_id": OWNED,
            "spec": spec or {"seed": 9, "minimum_artist_gap": 2},
            "name": "PlaylistIQ mix",
        },
    )


def test_export_writes_exact_previewed_order_in_batches(spotify: FakeSpotify) -> None:
    c = login("judy")
    c.post(f"/api/playlists/{OWNED}/sync")
    preview = c.post(f"/api/playlists/{OWNED}/preview", json={"seed": 9, "minimum_artist_gap": 2})
    expected = [q["uri"] for q in preview.json()["queue"]]

    r = _export(c, "judy-key-0001")
    assert r.status_code == 202
    job = c.get(f"/api/exports/{r.json()['id']}").json()
    assert job["status"] == "completed", job
    assert job["completed_items"] == job["total_items"] == 230
    assert job["batches_done"] == 3  # 100 + 100 + 30
    assert spotify.added[job["destination_playlist_id"]] == expected
    assert job["destination_url"].startswith("https://open.spotify.com/playlist/")


def test_same_idempotency_key_never_creates_a_second_playlist(spotify: FakeSpotify) -> None:
    c = login("kim")
    c.post(f"/api/playlists/{OWNED}/sync")
    first = _export(c, "kim-key-00001").json()
    again = _export(c, "kim-key-00001").json()
    assert first["id"] == again["id"]
    assert len(spotify.created) == 1


def test_retry_after_partial_failure_resumes_without_duplicates(
    spotify: FakeSpotify, monkeypatch: pytest.MonkeyPatch
) -> None:
    no_backoff(monkeypatch)
    c = login("leo")
    c.post(f"/api/playlists/{OWNED}/sync")
    # Second add-items call fails on every retry (initial + 4 retries = calls 2..6).
    spotify.fail_add_on_call = {2, 3, 4, 5, 6}
    job = _export(c, "leo-key-000001").json()
    status = c.get(f"/api/exports/{job['id']}").json()
    assert status["status"] == "failed"
    assert status["completed_items"] == 100
    dest = status["destination_playlist_id"]
    assert dest and len(spotify.added[dest]) == 100

    retried = c.post(f"/api/exports/{job['id']}/retry")
    assert retried.status_code == 202
    final = c.get(f"/api/exports/{job['id']}").json()
    assert final["status"] == "completed", final
    assert final["destination_playlist_id"] == dest
    assert len(spotify.created) == 1
    assert len(spotify.added[dest]) == 230 and len(set(spotify.added[dest])) == 230


def test_resume_refuses_if_destination_was_edited(
    spotify: FakeSpotify, monkeypatch: pytest.MonkeyPatch
) -> None:
    no_backoff(monkeypatch)
    c = login("mia")
    c.post(f"/api/playlists/{OWNED}/sync")
    spotify.fail_add_on_call = {2, 3, 4, 5, 6}
    job = _export(c, "mia-key-000001").json()
    dest = c.get(f"/api/exports/{job['id']}").json()["destination_playlist_id"]
    spotify.added[dest].insert(0, "spotify:track:somethingElse")
    c.post(f"/api/exports/{job['id']}/retry")
    final = c.get(f"/api/exports/{job['id']}").json()
    assert final["status"] == "failed" and "changed outside PlaylistIQ" in final["error"]


def test_export_rules(spotify: FakeSpotify) -> None:
    c = login("ned")
    c.post(f"/api/playlists/{OWNED}/sync")
    demo = c.post(
        "/api/exports",
        headers={"Idempotency-Key": "ned-key-000001"},
        json={"playlist_id": "demo-late-night", "spec": {"seed": 1}, "name": "x"},
    )
    assert demo.status_code == 422 and "Demo" in demo.json()["detail"]
    no_seed = _export(c, "ned-key-000002", {"minimum_artist_gap": 1})
    assert no_seed.status_code == 422 and "seed" in no_seed.json()["detail"]
    no_key = c.post("/api/exports", json={"playlist_id": OWNED, "spec": {"seed": 1}, "name": "x"})
    assert no_key.status_code == 422


def test_delete_me_removes_everything(spotify: FakeSpotify) -> None:
    c = login("olga")
    c.post(f"/api/playlists/{OWNED}/sync")
    _export(c, "olga-key-00001")
    from sqlalchemy.orm import Session as DB

    with DB(engine_for(get_settings().database_url)) as db:
        user = db.scalar(select(User).where(User.spotify_user_id == "olga"))
        assert user is not None
        uid = user.id
    assert db_count(PlaylistCache, user_id=uid) == 1 and db_count(ExportJob, user_id=uid) == 1

    assert c.delete("/api/me").status_code == 204
    assert db_count(User, id=uid) == 0
    assert db_count(SpotifyConnection, user_id=uid) == 0
    assert db_count(Session, user_id=uid) == 0
    assert db_count(PlaylistCache, user_id=uid) == 0
    assert db_count(ExportJob, user_id=uid) == 0
    assert c.get("/api/auth/me").json()["connected"] is False


def test_code_challenge_matches_verifier_sent_on_exchange(spotify: FakeSpotify) -> None:
    with TestClient(app, follow_redirects=False) as c:
        start = c.get("/api/auth/spotify/start")
        q = parse_qs(urlparse(start.headers["location"]).query)
        c.get("/api/auth/spotify/callback", params={"code": "code-pat", "state": q["state"][0]})
    sent = spotify.last_token_form
    assert sent["grant_type"] == "authorization_code" and sent["client_id"] == "test-client-id"
    assert "client_secret" not in sent
    assert code_challenge(sent["code_verifier"]) == q["code_challenge"][0]
