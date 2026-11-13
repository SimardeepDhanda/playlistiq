from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.engine.models import ShuffleMode
from app.engine.query_parser import Catalog, DeterministicQueryParser, ParseResult
from app.services.demo import Playlist
from tests.conftest import ids_by_name

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "benchmarks"))
import query_eval

parser = DeterministicQueryParser()


@pytest.fixture(scope="module")
def catalog(big: Playlist) -> Catalog:
    return Catalog.from_entries(big.entries)


def parse(text: str, catalog: Catalog) -> ParseResult:
    return parser.parse(text, catalog)


def test_only_artist(big: Playlist, catalog: Catalog) -> None:
    r = parse("Only Marlo Vance", catalog)
    assert r.spec is not None
    # The local file credited to "Marlo Vance" by name is merged with the real artist.
    assert set(r.spec.include_artist_ids) == set(ids_by_name(big.entries, "Marlo Vance"))


def test_no_artist(catalog: Catalog) -> None:
    r = parse("No Kiro", catalog)
    assert r.spec is not None and r.spec.exclude_artist_ids and not r.spec.include_artist_ids


def test_two_artists_except_album_includes_editions(big: Playlist, catalog: Catalog) -> None:
    r = parse("Marlo Vance and J. Calder except Overlook", catalog)
    assert r.spec is not None
    overlook = ids_by_name(big.entries, "Overlook", "album") + ids_by_name(
        big.entries, "Overlook (Deluxe)", "album"
    )
    assert sorted(r.spec.exclude_album_ids) == sorted(overlook)
    assert any("editions" in n for n in r.notes)


def test_artist_from_album(catalog: Catalog) -> None:
    r = parse("J. Calder from The Long Season", catalog)
    assert r.spec is not None
    assert len(r.spec.include_artist_ids) == 1 and len(r.spec.include_album_ids) == 1


def test_no_back_to_back(catalog: Catalog) -> None:
    r = parse("No same artist back-to-back", catalog)
    assert r.spec is not None
    assert r.spec.shuffle_mode is ShuffleMode.BALANCED and r.spec.minimum_artist_gap == 1
    assert not r.spec.exclude_artist_ids  # "no" here is about ordering, not exclusion


def test_contradiction_is_reported_not_resolved(catalog: Catalog) -> None:
    r = parse("only Kiro but exclude Kiro", catalog)
    assert r.spec is None and r.contradictions


def test_same_name_artists_ask_for_clarification(catalog: Catalog) -> None:
    r = parse("Only Echo", catalog)
    assert r.spec is None and r.draft_spec is not None
    assert len(r.ambiguities) == 1 and len(r.ambiguities[0].options) == 2
    assert all(o.detail.startswith("appears on") for o in r.ambiguities[0].options)


def test_album_title_collision(catalog: Catalog) -> None:
    assert parse("songs from Homecoming", catalog).ambiguities
    r = parse("Nia Solstice from Homecoming", catalog)
    assert r.spec is not None and len(r.spec.include_album_ids) == 1


def test_artist_album_name_collision_uses_cues(catalog: Catalog) -> None:
    assert parse("Gold Coast", catalog).ambiguities
    by = parse("songs by Gold Coast", catalog).spec
    album = parse("the Gold Coast album", catalog).spec
    assert by is not None and by.include_artist_ids and not by.include_album_ids
    assert album is not None and album.include_album_ids and not album.include_artist_ids


def test_unknown_names_are_never_invented(catalog: Catalog) -> None:
    r = parse("only Kendrick Lamar", catalog)
    assert r.unrecognized == ["kendrick lamar"]
    assert r.spec is not None and not r.spec.include_artist_ids


def test_unsupported_requests_explained(catalog: Catalog) -> None:
    r = parse("most played Kiro songs", catalog)
    assert r.unsupported and "Play counts" in r.unsupported[0]


def test_gap_and_seed_and_strict(catalog: Catalog) -> None:
    r = parse("keep artists 5 songs apart, strict, seed 42", catalog)
    assert r.spec is not None
    assert (r.spec.minimum_artist_gap, r.spec.strict_constraints, r.spec.seed) == (5, True, 42)


def test_overlong_query_rejected(catalog: Catalog) -> None:
    r = parse("x" * 600, catalog)
    assert r.spec is None and r.unsupported


def test_labeled_query_set_accuracy() -> None:
    report = query_eval.evaluate()
    assert report["queries"] >= 100
    failures = [r["query"] for r in report["rows"] if not r["ok"]]
    assert report["exact_parse_accuracy"] >= 0.95, failures
    assert report["selection_precision"] >= 0.99
    assert report["selection_recall"] >= 0.99
