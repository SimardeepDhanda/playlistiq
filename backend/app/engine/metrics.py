"""Evaluation metrics for orderings. Used by tests, benchmarks and the preview API."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from app.engine.models import PlaylistEntry


def is_valid_permutation(source: Sequence[PlaylistEntry], order: Sequence[PlaylistEntry]) -> bool:
    """Every selected entry appears exactly once and nothing else appears."""
    return Counter(e.entry_id for e in source) == Counter(e.entry_id for e in order) and len(
        {e.entry_id for e in order}
    ) == len(order)


def same_artist_pairs_within(order: Sequence[PlaylistEntry], window: int) -> int:
    """Pairs of entries at distance <= ``window`` that share any credited artist."""
    keys = [e.artist_keys() for e in order]
    count = 0
    for i in range(len(keys)):
        for d in range(1, window + 1):
            j = i + d
            if j < len(keys) and keys[i] & keys[j]:
                count += 1
    return count


def adjacent_overlap_rate(order: Sequence[PlaylistEntry]) -> float:
    if len(order) < 2:
        return 0.0
    return same_artist_pairs_within(order, 1) / (len(order) - 1)


def position_exposure(order: Sequence[PlaylistEntry]) -> dict[str, float]:
    """Mean normalized position (0 = first, 1 = last) per primary artist.

    Averaged over many seeds, a fair order puts every artist near 0.5.
    """
    if len(order) < 2:
        return {}
    sums: dict[str, float] = defaultdict(float)
    counts: Counter[str] = Counter()
    for pos, e in enumerate(order):
        if e.artists:
            name = e.artists[0].name
            sums[name] += pos / (len(order) - 1)
            counts[name] += 1
    return {a: sums[a] / counts[a] for a in sums}


def positional_agreement(a: Sequence[PlaylistEntry], b: Sequence[PlaylistEntry]) -> float:
    """Share of positions holding the same entry in two orderings. Near 1/n for
    independent shuffles; near 1 means outputs are nearly identical."""
    if not a:
        return 0.0
    return sum(x.entry_id == y.entry_id for x, y in zip(a, b, strict=True)) / len(a)


@dataclass(frozen=True)
class OrderMetrics:
    entries: int
    adjacent_overlap_rate: float
    same_artist_pairs_within_3: int
    same_artist_pairs_within_5: int


def summarize(order: Sequence[PlaylistEntry]) -> OrderMetrics:
    return OrderMetrics(
        entries=len(order),
        adjacent_overlap_rate=round(adjacent_overlap_rate(order), 4),
        same_artist_pairs_within_3=same_artist_pairs_within(order, 3),
        same_artist_pairs_within_5=same_artist_pairs_within(order, 5),
    )
