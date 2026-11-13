from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.engine.filters import apply_filters
from app.engine.models import QuerySpec
from app.services.demo import Playlist
from tests.conftest import ids_by_name, make_entry


def test_artist_and_album_returns_exactly_the_matching_entries(big: Playlist) -> None:
    calder = ids_by_name(big.entries, "J. Calder")
    long_season = ids_by_name(big.entries, "The Long Season", "album")
    spec = QuerySpec(include_artist_ids=calder, include_album_ids=long_season)

    result = apply_filters(big.entries, spec)

    expected = [
        e
        for e in big.entries
        if any(a.name == "J. Calder" for a in e.artists)
        and e.album is not None
        and e.album.name == "The Long Season"
    ]
    assert result.matched == expected
    assert result.match_count == len(expected) > 0


def test_excluded_album_never_appears(big: Playlist) -> None:
    marlo = ids_by_name(big.entries, "Marlo Vance")
    overlook = ids_by_name(big.entries, "Overlook", "album")
    result = apply_filters(big.entries, QuerySpec(include_artist_ids=marlo, exclude_album_ids=overlook))
    assert result.match_count > 0
    assert all(e.album is None or e.album.name != "Overlook" for e in result.matched)
    assert result.removed_by_exclusion == sum(
        1
        for e in big.entries
        if any(a.key in marlo for a in e.artists) and e.album and e.album.name == "Overlook"
    )


def test_collaboration_matches_any_credited_artist() -> None:
    entries = [make_entry(0, ["Lead", "Guest"]), make_entry(1, ["Lead"]), make_entry(2, ["Other"])]
    result = apply_filters(entries, QuerySpec(include_artist_ids=["ar-Guest"]))
    assert [e.position for e in result.matched] == [0]


def test_primary_artist_only_ignores_features() -> None:
    entries = [make_entry(0, ["Lead", "Guest"]), make_entry(1, ["Guest", "Lead"])]
    spec = QuerySpec(include_artist_ids=["ar-Guest"], primary_artist_only=True)
    assert [e.position for e in apply_filters(entries, spec).matched] == [1]


def test_duplicate_tracks_are_kept_as_separate_entries() -> None:
    entries = [
        make_entry(0, ["A"], track_id="same"),
        make_entry(1, ["B"]),
        make_entry(2, ["A"], track_id="same"),
    ]
    result = apply_filters(entries, QuerySpec(include_artist_ids=["ar-A"]))
    assert [e.entry_id for e in result.matched] == ["p:0", "p:2"]


def test_duplicates_in_demo_playlist_survive_filtering(big: Playlist) -> None:
    result = apply_filters(big.entries, QuerySpec())
    track_ids = [e.track_id for e in result.matched if e.track_id]
    assert len(track_ids) > len(set(track_ids))
    assert result.matched == list(big.entries)


def test_precedence_or_within_and_across_exclusion_wins() -> None:
    entries = [
        make_entry(0, ["A"], album="X"),
        make_entry(1, ["B"], album="X"),
        make_entry(2, ["A"], album="Y"),
        make_entry(3, ["C"], album="X"),
        make_entry(4, ["A", "C"], album="X"),
    ]
    spec = QuerySpec(
        include_artist_ids=["ar-A", "ar-B"],  # OR
        include_album_ids=["al-X"],  # AND with the artist rule
        exclude_artist_ids=["ar-C"],  # removes entry 4 even though A matches
    )
    assert [e.position for e in apply_filters(entries, spec).matched] == [0, 1]


def test_empty_spec_keeps_everything_in_original_order() -> None:
    entries = [make_entry(i, [f"A{i % 3}"]) for i in range(10)]
    assert apply_filters(entries, QuerySpec()).matched == entries


def test_zero_results() -> None:
    entries = [make_entry(0, ["A"])]
    result = apply_filters(entries, QuerySpec(include_artist_ids=["ar-Nobody"]))
    assert result.match_count == 0


def test_contradictory_spec_is_rejected() -> None:
    with pytest.raises(ValidationError, match="both included and excluded"):
        QuerySpec(include_artist_ids=["x"], exclude_artist_ids=["x"])
    with pytest.raises(ValidationError):
        QuerySpec(include_album_ids=["y"], exclude_album_ids=["y"])


def test_spec_limits_are_validated() -> None:
    with pytest.raises(ValidationError):
        QuerySpec(include_artist_ids=["a"] * 201)
    with pytest.raises(ValidationError):
        QuerySpec(minimum_artist_gap=51)
    with pytest.raises(ValidationError):
        QuerySpec.model_validate({"unknown_field": 1})


def test_local_files_match_by_name_key(big: Playlist) -> None:
    keys = ids_by_name(big.entries, "Basement Static")
    assert keys == ["local-artist:basement static"]
    result = apply_filters(big.entries, QuerySpec(include_artist_ids=keys))
    assert result.match_count == 2
    assert all(e.is_local for e in result.matched)


def test_entries_without_album_survive_album_exclusion() -> None:
    entries = [make_entry(0, ["A"], album=None), make_entry(1, ["A"], album="X")]
    spec = QuerySpec(exclude_album_ids=["al-X"])
    assert [e.position for e in apply_filters(entries, spec).matched] == [0]


def test_explanations(big: Playlist) -> None:
    calder = ids_by_name(big.entries, "J. Calder")
    result = apply_filters(big.entries, QuerySpec(include_artist_ids=calder), explain=True)
    first = result.matched[0]
    assert result.reasons[first.entry_id] == ["artist: J. Calder"]


def test_seed_must_fit_in_a_javascript_number() -> None:
    QuerySpec(seed=2**53 - 1)
    with pytest.raises(ValidationError):
        QuerySpec(seed=2**53)
