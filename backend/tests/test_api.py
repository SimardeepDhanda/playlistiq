from __future__ import annotations

from collections.abc import Iterator

import pytest
import respx
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app, headers={"X-PlaylistIQ": "1"}) as c:
        yield c


def test_health(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["demo_mode"] is True


def test_demo_mode_makes_no_external_calls(client: TestClient) -> None:
    with respx.mock(assert_all_called=False) as router:
        client.get("/api/playlists")
        r = client.post("/api/playlists/demo-late-night/preview", json={"seed": 1})
        assert r.status_code == 200
        client.post("/api/parse-query", json={"playlist_id": "demo-late-night", "text": "Kiro"})
        assert router.calls.call_count == 0


def test_list_playlists(client: TestClient) -> None:
    body = client.get("/api/playlists").json()
    assert body["mode"] == "demo"
    sizes = {p["id"]: p["entry_count"] for p in body["playlists"]}
    assert sizes["demo-late-night"] >= 2000


def test_tracks_pagination(client: TestClient) -> None:
    page = client.get("/api/playlists/demo-late-night/tracks?offset=2390&limit=50").json()
    assert page["total"] == 2394 and len(page["items"]) == 4
    assert client.get("/api/playlists/demo-late-night/tracks?limit=500").status_code == 422


def test_unknown_or_invalid_playlist(client: TestClient) -> None:
    assert client.get("/api/playlists/nope/tracks").status_code == 404
    assert client.get("/api/playlists/bad%20id!/tracks").status_code == 422
    assert client.post("/api/playlists/nope/preview", json={}).status_code == 404


def test_facets(client: TestClient) -> None:
    body = client.get("/api/playlists/demo-late-night/facets").json()
    assert body["artists"][0]["name"] == "Marlo Vance"
    names = [a["name"] for a in body["artists"]]
    assert names.count("Echo") == 2


def test_preview_round_trip(client: TestClient) -> None:
    facets = client.get("/api/playlists/demo-late-night/facets").json()
    marlo = next(a["id"] for a in facets["artists"] if a["name"] == "Marlo Vance")
    overlook = [a["id"] for a in facets["albums"] if a["name"].startswith("Overlook")]
    spec = {
        "include_artist_ids": [marlo],
        "exclude_album_ids": overlook,
        "shuffle_mode": "random",
        "seed": 99,
    }
    body = client.post("/api/playlists/demo-late-night/preview", json=spec).json()
    assert body["match_count"] == len(body["queue"]) > 0
    assert body["seed"] == 99 and body["status"] == "ok"
    assert not any(q["album"]["name"].startswith("Overlook") for q in body["queue"])
    assert body["applied_rules"][0].startswith("Only songs where any credited artist is")
    again = client.post("/api/playlists/demo-late-night/preview", json=spec).json()
    assert [q["entry_id"] for q in again["queue"]] == [q["entry_id"] for q in body["queue"]]


def test_preview_strict_infeasible(client: TestClient) -> None:
    body = client.post(
        "/api/playlists/demo-calder-deep-dive/preview",
        json={"shuffle_mode": "balanced", "strict_constraints": True, "seed": 1},
    ).json()
    assert body["status"] == "infeasible" and body["queue"] == []
    assert body["match_count"] == 45


def test_preview_rejects_contradiction(client: TestClient) -> None:
    r = client.post(
        "/api/playlists/demo-late-night/preview",
        json={"include_artist_ids": ["x"], "exclude_artist_ids": ["x"]},
    )
    assert r.status_code == 422


def test_preview_zero_matches(client: TestClient) -> None:
    body = client.post(
        "/api/playlists/demo-late-night/preview", json={"include_artist_ids": ["missing"]}
    ).json()
    assert body["match_count"] == 0 and body["queue"] == []
    assert "No entries" in body["notes"][0]


def test_parse_query(client: TestClient) -> None:
    r = client.post(
        "/api/parse-query",
        json={"playlist_id": "demo-late-night", "text": "J. Calder from The Long Season"},
    )
    body = r.json()
    assert r.status_code == 200
    assert len(body["spec"]["include_artist_ids"]) == 1
    assert len(body["spec"]["include_album_ids"]) == 1
    too_long = {"playlist_id": "demo-late-night", "text": "x" * 501}
    assert client.post("/api/parse-query", json=too_long).status_code == 422


def test_writes_without_csrf_header_are_refused() -> None:
    with TestClient(app) as c:
        r = c.post("/api/playlists/demo-late-night/preview", json={})
        assert r.status_code == 403
