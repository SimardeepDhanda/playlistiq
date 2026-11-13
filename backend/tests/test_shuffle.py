from __future__ import annotations

import itertools
from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest

from app.engine.filters import apply_filters
from app.engine.metrics import is_valid_permutation, positional_agreement
from app.engine.models import QuerySpec, ShuffleMode
from app.engine.shuffle import (
    ShuffleStatus,
    find_violations,
    fisher_yates,
    shuffle,
    shuffle_balanced,
    shuffle_random,
    shuffle_recently_added,
)
from app.services.demo import Playlist
from tests.conftest import ids_by_name, make_entries, make_entry

# ------------------------------------------------------------------ random


def test_random_is_a_permutation_of_entries(big: Playlist) -> None:
    result = shuffle_random(big.entries, seed=7)
    assert is_valid_permutation(big.entries, result.order)
    assert result.order != list(big.entries)


def test_random_keeps_duplicate_occurrences() -> None:
    entries = [make_entry(0, ["A"], track_id="dup"), make_entry(1, ["A"], track_id="dup")]
    order = shuffle_random(entries, seed=1).order
    assert sorted(e.entry_id for e in order) == ["p:0", "p:1"]


def test_same_seed_same_output(big: Playlist) -> None:
    for mode in ShuffleMode:
        a = shuffle(big.entries, mode, seed=123, minimum_artist_gap=3)
        b = shuffle(big.entries, mode, seed=123, minimum_artist_gap=3)
        assert [e.entry_id for e in a.order] == [e.entry_id for e in b.order]


def test_missing_seed_is_generated_and_reproducible(big: Playlist) -> None:
    first = shuffle_balanced(big.entries, seed=None, minimum_artist_gap=2)
    again = shuffle_balanced(big.entries, seed=first.seed, minimum_artist_gap=2)
    assert first.order == again.order


def test_fisher_yates_is_uniform_on_small_input() -> None:
    """Chi-square goodness of fit over all 24 permutations of 4 items.

    With 23 degrees of freedom the 99.9th percentile is 49.73. The RNG is seeded,
    so the test is deterministic.
    """
    from random import Random

    rng = Random(2026)
    items = [0, 1, 2, 3]
    trials = 48_000
    counts = Counter(tuple(fisher_yates(items, rng)) for _ in range(trials))
    perms = list(itertools.permutations(items))
    assert set(counts) == set(perms)
    expected = trials / len(perms)
    chi2 = sum((counts[p] - expected) ** 2 / expected for p in perms)
    assert chi2 < 49.73


def test_random_outputs_differ_across_seeds(big: Playlist) -> None:
    orders = [shuffle_random(big.entries, seed=s).order for s in range(5)]
    for a, b in itertools.combinations(orders, 2):
        assert positional_agreement(a, b) < 0.01


# ---------------------------------------------------------------- balanced


@pytest.mark.parametrize("gap", [1, 2, 3, 5, 7])
@pytest.mark.parametrize("seed", range(8))
def test_strict_balanced_never_violates_the_gap(big: Playlist, gap: int, seed: int) -> None:
    result = shuffle_balanced(big.entries, seed=seed, minimum_artist_gap=gap, strict=True)
    assert result.status is ShuffleStatus.OK
    assert is_valid_permutation(big.entries, result.order)
    assert find_violations(result.order, gap) == []


def test_strict_gap_beyond_the_bound_is_reported_infeasible(big: Playlist) -> None:
    # Marlo Vance is on ~290 of 2,394 entries; (count - 1) * (gap + 1) + 1 <= 2394 caps gap at 7.
    result = shuffle_balanced(big.entries, seed=1, minimum_artist_gap=8, strict=True)
    assert result.status is ShuffleStatus.INFEASIBLE
    assert result.order == []
    assert "Marlo Vance" in result.notes[0]


def test_relaxed_mode_reports_exact_violations(big: Playlist) -> None:
    result = shuffle_balanced(big.entries, seed=1, minimum_artist_gap=10, strict=False)
    assert result.status is ShuffleStatus.RELAXED
    assert is_valid_permutation(big.entries, result.order)
    independent = find_violations(result.order, 10)
    assert len(independent) == len(result.violations) > 0
    assert [v.position for v in independent] == [v.position for v in result.violations]


def test_relaxed_mode_reports_ok_only_when_true(demo: dict[str, Playlist]) -> None:
    entries = demo["demo-road-trip"].entries
    result = shuffle_balanced(entries, seed=3, minimum_artist_gap=2)
    assert result.status is ShuffleStatus.OK
    assert find_violations(result.order, 2) == []


def test_balanced_reduces_adjacent_repeats_vs_random(big: Playlist) -> None:
    from app.engine.metrics import adjacent_overlap_rate

    rnd = [adjacent_overlap_rate(shuffle_random(big.entries, seed=s).order) for s in range(5)]
    bal = [
        adjacent_overlap_rate(shuffle_balanced(big.entries, seed=s, minimum_artist_gap=1).order)
        for s in range(5)
    ]
    assert min(rnd) > 0.01
    assert max(bal) == 0.0


def test_single_artist_strict_is_infeasible(demo: dict[str, Playlist]) -> None:
    entries = demo["demo-calder-deep-dive"].entries
    result = shuffle_balanced(entries, seed=1, minimum_artist_gap=1, strict=True)
    assert result.status is ShuffleStatus.INFEASIBLE
    assert "cannot be increased" in result.notes[0]


def test_single_artist_relaxed_falls_back_to_random(demo: dict[str, Playlist]) -> None:
    entries = demo["demo-calder-deep-dive"].entries
    result = shuffle_balanced(entries, seed=1, minimum_artist_gap=1)
    assert result.status is ShuffleStatus.RELAXED
    assert is_valid_permutation(entries, result.order)
    assert len(result.violations) == len(entries) - 1
    assert any("uniform random" in n for n in result.notes)


def test_single_artist_filter_on_big_playlist(big: Playlist) -> None:
    calder = ids_by_name(big.entries, "J. Calder")
    porch = ids_by_name(big.entries, "Porch Light", "album")
    picked = apply_filters(big.entries, QuerySpec(include_artist_ids=calder, include_album_ids=porch)).matched
    result = shuffle_balanced(picked, seed=4, minimum_artist_gap=1, strict=True)
    assert result.status is ShuffleStatus.INFEASIBLE


def test_tight_but_feasible_case_is_solved() -> None:
    # A appears 3 times in 5 slots with gap 1: only A x A x A works.
    entries = make_entries(["A", "A", "A", "B", "C"])
    for seed in range(20):
        result = shuffle_balanced(entries, seed=seed, minimum_artist_gap=1, strict=True)
        assert result.status is ShuffleStatus.OK
        assert [e.artists[0].name for e in result.order][::2] == ["A", "A", "A"]


def test_collaborations_can_make_a_gap_impossible() -> None:
    # Every pair of entries shares an artist, so any order puts two sharing
    # entries next to each other. The simple count bound does not see this.
    entries = make_entries([("A", "B"), ("B", "C"), ("A", "C")])
    result = shuffle_balanced(entries, seed=1, minimum_artist_gap=1, strict=True)
    assert result.status is ShuffleStatus.INFEASIBLE
    assert "Exhaustive search" in result.notes[0]


def test_collaborations_respected_in_gap() -> None:
    entries = make_entries(["A", ("A", "B"), "B", "C", "D", "E", "C", "D"])
    for seed in range(30):
        result = shuffle_balanced(entries, seed=seed, minimum_artist_gap=1, strict=True)
        assert result.status is ShuffleStatus.OK
        assert find_violations(result.order, 1) == []


def test_entries_without_artists_never_conflict() -> None:
    entries = make_entries([(), (), "A", "A"])
    result = shuffle_balanced(entries, seed=0, minimum_artist_gap=1, strict=True)
    assert result.status is ShuffleStatus.OK
    assert find_violations(result.order, 1) == []


def test_gap_zero_and_tiny_inputs() -> None:
    assert shuffle_balanced([], seed=1).order == []
    one = make_entries(["A"])
    assert shuffle_balanced(one, seed=1).order == one
    two = make_entries(["A", "A"])
    assert shuffle_balanced(two, seed=1, minimum_artist_gap=0).status is ShuffleStatus.OK


def test_balanced_varies_across_seeds(big: Playlist) -> None:
    orders = [shuffle_balanced(big.entries, seed=s, minimum_artist_gap=3).order for s in range(5)]
    for a, b in itertools.combinations(orders, 2):
        assert positional_agreement(a, b) < 0.02


# ----------------------------------------------------------- recently added


def test_recently_added_orders_by_band() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    entries = [
        make_entry(i, ["A"]).model_copy(update={"added_at": base - timedelta(days=d)})
        for i, d in enumerate([100, 1, 40, 2, 70, 0])
    ]
    undated = make_entry(6, ["B"])
    result = shuffle_recently_added([*entries, undated], seed=3, band_days=30)
    days = [(base - e.added_at).days if e.added_at else None for e in result.order]
    assert sorted(days[:3]) == [0, 1, 2]  # newest band first, shuffled inside
    assert days[3:6] == [40, 70, 100]
    assert days[6] is None
    assert "not a uniform shuffle" in result.notes[0]


def test_recently_added_strict_newest_first(big: Playlist) -> None:
    result = shuffle_recently_added(big.entries, seed=1, band_days=0)
    times = [e.added_at for e in result.order]
    assert times == sorted(times, reverse=True)  # type: ignore[type-var]
    assert is_valid_permutation(big.entries, result.order)
