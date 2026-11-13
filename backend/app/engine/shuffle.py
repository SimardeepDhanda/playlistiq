"""Ordering engines: true random, balanced (artist spacing) and recently added.

All engines operate on playlist *entries* (occurrences), never on unique track
IDs, so a song that appears twice in the playlist appears twice in the output.

Artist-gap semantics: with ``minimum_artist_gap = k`` the entry at position
``p`` must not share any credited artist with the entries at positions
``p-k .. p-1``. ``k = 1`` therefore means "no shared artist back-to-back".
"""

from __future__ import annotations

import heapq
import secrets
from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from random import Random

from app.engine.models import PlaylistEntry, ShuffleMode

NEVER = -(10**9)
RANDOMIZED_ATTEMPTS = 10
GREEDY_ATTEMPTS = 3
RELAXED_ATTEMPTS = 5
EXACT_SEARCH_MAX_ENTRIES = 60
EXACT_SEARCH_NODE_BUDGET = 200_000
# Sampling weight is entries_in_group * (remaining entries of its busiest artist) ** exponent.
# Higher exponents place heavy artists earlier: fewer dead ends and fewer violations
# when the gap is impossible, but the heavy artist drifts toward the front.
# benchmarks/shuffle_bench.py measures this; 0.5 kept the dominant artist's mean
# position within about 0.01 of the middle, 1.0 front-loaded it (about 0.47).
WEIGHT_EXPONENT = 0.5
WEIGHT_EXPONENT_OVERLOADED = 1.0  # used when the gap is already known to be unreachable


class ShuffleStatus(StrEnum):
    OK = "ok"  # every requested constraint is satisfied
    RELAXED = "relaxed"  # non-strict mode; violations are listed exactly
    INFEASIBLE = "infeasible"  # strict mode; proven that no valid order exists
    NOT_FOUND = "not_found"  # strict mode; search budget ran out, feasibility unknown


@dataclass(frozen=True)
class Violation:
    position: int
    entry_id: str
    conflicting_position: int
    shared_artists: tuple[str, ...]


@dataclass
class ShuffleResult:
    order: list[PlaylistEntry]
    mode: ShuffleMode
    seed: int
    status: ShuffleStatus
    minimum_artist_gap: int = 0
    strict: bool = False
    violations: list[Violation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    attempts: int = 1


def resolve_seed(seed: int | None) -> int:
    """Use the caller's seed, or draw one so the result can be reproduced and shared."""
    # Seeds stay below 2**53 so they survive a round trip through JavaScript numbers.
    return seed if seed is not None else secrets.randbits(53)


# --------------------------------------------------------------------------- random


def fisher_yates[T](items: Sequence[T], rng: Random) -> list[T]:
    """Uniform random permutation (Durstenfeld's in-place Fisher-Yates)."""
    out = list(items)
    for i in range(len(out) - 1, 0, -1):
        j = rng.randrange(i + 1)
        out[i], out[j] = out[j], out[i]
    return out


def shuffle_random(entries: Sequence[PlaylistEntry], seed: int | None = None) -> ShuffleResult:
    seed = resolve_seed(seed)
    order = fisher_yates(entries, Random(seed))
    return ShuffleResult(
        order=order,
        mode=ShuffleMode.RANDOM,
        seed=seed,
        status=ShuffleStatus.OK,
        notes=["Fisher-Yates shuffle: every ordering of the selected entries is equally likely."],
    )


# --------------------------------------------------------------------- recently added


def shuffle_recently_added(
    entries: Sequence[PlaylistEntry], seed: int | None = None, band_days: int = 30
) -> ShuffleResult:
    """Newest additions first. Entries are grouped into ``band_days``-wide bands
    counted back from the newest addition and shuffled only within a band.
    ``band_days = 0`` gives a strict newest-first order. Entries with no
    ``added_at`` go last, shuffled among themselves."""
    seed = resolve_seed(seed)
    rng = Random(seed)
    dated = [e for e in entries if e.added_at is not None]
    undated = [e for e in entries if e.added_at is None]

    order: list[PlaylistEntry] = []
    if dated:
        newest: datetime = max(e.added_at for e in dated if e.added_at is not None)
        if band_days == 0:
            order = sorted(dated, key=lambda e: (-(e.added_at.timestamp() if e.added_at else 0), e.position))
        else:
            bands: dict[int, list[PlaylistEntry]] = defaultdict(list)
            for e in sorted(dated, key=lambda e: e.position):
                assert e.added_at is not None
                bands[(newest - e.added_at).days // band_days].append(e)
            for band in sorted(bands):
                order.extend(fisher_yates(bands[band], rng))
    order.extend(fisher_yates(undated, rng))

    notes = [
        "Recently added first. This is not a uniform shuffle: newer additions are "
        "deliberately placed earlier."
    ]
    if band_days:
        notes.append(f"Entries are shuffled within {band_days}-day bands.")
    if undated:
        notes.append(f"{len(undated)} entries have no added date and are placed last.")
    return ShuffleResult(
        order=order,
        mode=ShuffleMode.RECENTLY_ADDED,
        seed=seed,
        status=ShuffleStatus.OK,
        notes=notes,
    )


# --------------------------------------------------------------------------- balanced


class _Fenwick:
    """Prefix sums over group weights for O(log n) weighted sampling."""

    def __init__(self, size: int) -> None:
        self.n = size
        self.tree = [0.0] * (size + 1)
        self.values = [0.0] * size

    def set(self, i: int, value: float) -> None:
        delta = value - self.values[i]
        if delta == 0:
            return
        self.values[i] = value
        i += 1
        while i <= self.n:
            self.tree[i] += delta
            i += i & -i

    def total(self) -> float:
        i, s = self.n, 0.0
        while i > 0:
            s += self.tree[i]
            i -= i & -i
        return s

    def find(self, target: float) -> int:
        """Smallest index whose prefix sum exceeds ``target``."""
        pos, step = 0, 1 << self.n.bit_length()
        while step:
            nxt = pos + step
            if nxt <= self.n and self.tree[nxt] <= target:
                pos = nxt
                target -= self.tree[nxt]
            step >>= 1
        return min(pos, self.n - 1)


class _DeadEnd(Exception):
    pass


@dataclass
class _Groups:
    """Entries grouped by their exact set of credited artists.

    Entries in one group are interchangeable as far as spacing is concerned, so
    the search chooses a group and then takes a uniformly random entry from it.
    """

    artist_sets: list[tuple[str, ...]]
    members: list[list[PlaylistEntry]]
    artist_groups: dict[str, list[int]]
    artist_counts: dict[str, int]
    artist_names: dict[str, str]

    @classmethod
    def build(cls, entries: Sequence[PlaylistEntry]) -> _Groups:
        index: dict[frozenset[str], int] = {}
        artist_sets: list[tuple[str, ...]] = []
        members: list[list[PlaylistEntry]] = []
        artist_groups: dict[str, list[int]] = defaultdict(list)
        counts: dict[str, int] = defaultdict(int)
        names: dict[str, str] = {}
        for e in entries:
            keys = e.artist_keys()
            for a in e.artists:
                names.setdefault(a.key, a.name)
            for k in keys:
                counts[k] += 1
            g = index.get(keys)
            if g is None:
                g = len(artist_sets)
                index[keys] = g
                artist_sets.append(tuple(sorted(keys)))
                members.append([])
                for k in keys:
                    artist_groups[k].append(g)
            members[g].append(e)
        return cls(artist_sets, members, dict(artist_groups), dict(counts), names)


def _necessary_condition_failures(counts: dict[str, int], n: int, gap: int) -> list[tuple[str, int, int]]:
    """Artists whose count alone makes the gap impossible.

    An artist on ``c`` entries needs at least ``(c - 1) * (gap + 1) + 1`` slots.
    Returns ``(artist_key, count, largest_feasible_gap)`` for each failure.
    """
    failures = []
    for a, c in counts.items():
        if c > 1 and (c - 1) * (gap + 1) + 1 > n:
            largest = (n - 1) // (c - 1) - 1
            failures.append((a, c, largest))
    return failures


class _BalancedRun:
    """One construction attempt. ``policy`` is "weighted" (randomized, favouring
    artists with many entries still to place) or "greedy" (always the artist
    with the most remaining entries, random tie-break)."""

    def __init__(
        self,
        groups: _Groups,
        gap: int,
        rng: Random,
        policy: str,
        allow_violations: bool,
        exponent: float = WEIGHT_EXPONENT,
    ) -> None:
        self.exponent = exponent
        self.g = groups
        self.gap = gap
        self.rng = rng
        self.policy = policy
        self.allow_violations = allow_violations
        self.pools = [fisher_yates(m, rng) for m in groups.members]
        # Groups holding an artist placed within the last ``gap`` slots are
        # blocked and get zero sampling weight, so every weighted draw is valid.
        self.blocked = [0] * len(groups.members)
        self.window: deque[tuple[int, tuple[str, ...]]] = deque()
        self.remaining = dict(groups.artist_counts)
        self.last_pos: dict[str, int] = dict.fromkeys(groups.artist_counts, NEVER)
        self.heap = [(-c, a) for a, c in self.remaining.items()]
        heapq.heapify(self.heap)
        self.tree = _Fenwick(len(groups.members))
        for gi in range(len(groups.members)):
            self._reweigh(gi)
        self.violations: list[Violation] = []

    # weights ---------------------------------------------------------------
    def _weight(self, gi: int) -> float:
        size = len(self.pools[gi])
        if size == 0 or self.blocked[gi]:
            return 0.0
        arts = self.g.artist_sets[gi]
        pressure = max((self.remaining[a] for a in arts), default=1)
        return float(size * pressure**self.exponent)

    def _reweigh(self, gi: int) -> None:
        self.tree.set(gi, self._weight(gi))

    # constraint helpers ----------------------------------------------------
    def _eligible(self, gi: int, pos: int) -> bool:
        return self.blocked[gi] == 0

    def _release(self, pos: int) -> None:
        """Unblock artists whose last placement just left the window."""
        while self.window and pos - self.window[0][0] > self.gap:
            placed_at, arts = self.window.popleft()
            for a in arts:
                if self.last_pos[a] == placed_at:  # not placed again since
                    for gi in self.g.artist_groups[a]:
                        self.blocked[gi] -= 1
                        if self.blocked[gi] == 0:
                            self._reweigh(gi)

    def _forced_artists(self, pos: int, slots_left: int) -> list[str]:
        """Artists that must be placed right now for the rest to stay feasible.

        Raises ``_DeadEnd`` when some artist can no longer fit at all.
        """
        threshold = max(1, (slots_left - 1 - self.gap) // (self.gap + 1) + 1)
        forced: list[str] = []
        popped: list[tuple[int, str]] = []
        dead = False
        while self.heap and -self.heap[0][0] >= threshold:
            neg, a = heapq.heappop(self.heap)
            if -neg != self.remaining[a]:
                continue  # stale heap record
            popped.append((neg, a))
            c = -neg
            wait = max(0, self.last_pos[a] + self.gap + 1 - pos)
            need = wait + (c - 1) * (self.gap + 1)
            if need > slots_left - 1:
                dead = True
            elif need == slots_left - 1 and wait == 0:
                forced.append(a)
        for item in popped:
            heapq.heappush(self.heap, item)
        if dead and not self.allow_violations:
            raise _DeadEnd
        return forced

    def _choose(self, pos: int, slots_left: int) -> int:
        forced = self._forced_artists(pos, slots_left)
        if forced:
            need = set(forced)
            cands = [
                gi
                for gi in self.g.artist_groups[forced[0]]
                if self.pools[gi] and need <= set(self.g.artist_sets[gi]) and self._eligible(gi, pos)
            ]
            if cands:
                return self._pick(cands)
            if not self.allow_violations:
                raise _DeadEnd

        if self.policy == "weighted":
            total = self.tree.total()
            if total > 1e-9:
                gi = self.tree.find(self.rng.random() * total)
                if self.pools[gi] and not self.blocked[gi]:
                    return gi
                # Floating-point drift in the prefix sums; fall through to a scan.

        cands = [gi for gi, p in enumerate(self.pools) if p and self._eligible(gi, pos)]
        if cands:
            return self._pick(cands)
        if not self.allow_violations:
            raise _DeadEnd
        return self._least_bad(pos)

    def _pick(self, cands: list[int]) -> int:
        if self.policy == "greedy":
            best = max(self._pressure(gi) for gi in cands)
            top = [gi for gi in cands if self._pressure(gi) == best]
            return top[self.rng.randrange(len(top))]
        weights = [self._weight(gi) for gi in cands]
        return self.rng.choices(cands, weights=weights, k=1)[0]

    def _pressure(self, gi: int) -> int:
        return max((self.remaining[a] for a in self.g.artist_sets[gi]), default=0)

    def _least_bad(self, pos: int) -> int:
        """Relaxed mode: the group whose conflict lies furthest back."""
        best_pen, best = None, []
        for gi, pool in enumerate(self.pools):
            if not pool:
                continue
            pen = max(
                (self.gap + 1 - (pos - self.last_pos[a]) for a in self.g.artist_sets[gi]),
                default=0,
            )
            if best_pen is None or pen < best_pen:
                best_pen, best = pen, [gi]
            elif pen == best_pen:
                best.append(gi)
        return best[self.rng.randrange(len(best))]

    # main loop -------------------------------------------------------------
    def run(self) -> list[PlaylistEntry]:
        n = sum(len(p) for p in self.pools)
        order: list[PlaylistEntry] = []
        for pos in range(n):
            self._release(pos)
            gi = self._choose(pos, n - pos)
            entry = self.pools[gi].pop()
            arts = self.g.artist_sets[gi]
            clash = [a for a in arts if pos - self.last_pos[a] <= self.gap]
            if clash:
                self.violations.append(
                    Violation(
                        position=pos,
                        entry_id=entry.entry_id,
                        conflicting_position=max(self.last_pos[a] for a in clash),
                        shared_artists=tuple(sorted(self.g.artist_names[a] for a in clash)),
                    )
                )
            touched = {gi}
            if self.gap > 0:
                for a in arts:
                    if pos - self.last_pos[a] > self.gap:  # newly blocked
                        for g2 in self.g.artist_groups[a]:
                            self.blocked[g2] += 1
                self.window.append((pos, arts))
            for a in arts:
                self.last_pos[a] = pos
                self.remaining[a] -= 1
                heapq.heappush(self.heap, (-self.remaining[a], a))
                touched.update(self.g.artist_groups[a])
            for t in touched:
                self._reweigh(t)
            order.append(entry)
        return order


def _exact_search(groups: _Groups, gap: int, rng: Random) -> tuple[list[int] | None, bool]:
    """Exhaustive DFS over group sequences for small inputs.

    Returns ``(sequence, exhausted)``. ``sequence`` is None when no valid order
    was found; ``exhausted`` is True only when the whole space was searched, in
    which case "no order" is a proof of infeasibility.
    """
    sizes = [len(m) for m in groups.members]
    n = sum(sizes)
    remaining = dict(groups.artist_counts)
    last = dict.fromkeys(remaining, NEVER)
    seq: list[int] = []
    nodes = 0
    order_hint = list(range(len(sizes)))
    rng.shuffle(order_hint)

    def feasible_tail(pos: int) -> bool:
        slots = n - pos
        for a, c in remaining.items():
            if c:
                wait = max(0, last[a] + gap + 1 - pos)
                if wait + (c - 1) * (gap + 1) > slots - 1:
                    return False
        return True

    def dfs(pos: int) -> bool:
        nonlocal nodes
        if pos == n:
            return True
        nodes += 1
        if nodes > EXACT_SEARCH_NODE_BUDGET or not feasible_tail(pos):
            return False
        cands = [
            gi for gi in order_hint if sizes[gi] and all(pos - last[a] > gap for a in groups.artist_sets[gi])
        ]
        cands.sort(key=lambda gi: -max((remaining[a] for a in groups.artist_sets[gi]), default=0))
        for gi in cands:
            saved = {a: last[a] for a in groups.artist_sets[gi]}
            sizes[gi] -= 1
            for a in groups.artist_sets[gi]:
                remaining[a] -= 1
                last[a] = pos
            seq.append(gi)
            if dfs(pos + 1):
                return True
            seq.pop()
            sizes[gi] += 1
            for a in groups.artist_sets[gi]:
                remaining[a] += 1
                last[a] = saved[a]
        return False

    found = dfs(0)
    return (list(seq) if found else None), nodes <= EXACT_SEARCH_NODE_BUDGET


def shuffle_balanced(
    entries: Sequence[PlaylistEntry],
    seed: int | None = None,
    minimum_artist_gap: int = 1,
    strict: bool = False,
) -> ShuffleResult:
    seed = resolve_seed(seed)
    rng = Random(seed)
    gap = minimum_artist_gap
    n = len(entries)

    def result(order: list[PlaylistEntry], status: ShuffleStatus, **kw: object) -> ShuffleResult:
        return ShuffleResult(
            order=order,
            mode=ShuffleMode.BALANCED,
            seed=seed,
            status=status,
            minimum_artist_gap=gap,
            strict=strict,
            **kw,  # type: ignore[arg-type]
        )

    if n <= 1 or gap == 0:
        note = (
            "Artist gap is 0, so there is nothing to balance; used a uniform shuffle."
            if gap == 0
            else "Nothing to balance with fewer than two entries."
        )
        return result(fisher_yates(entries, rng), ShuffleStatus.OK, notes=[note])

    groups = _Groups.build(entries)
    notes: list[str] = []
    universal = [a for a, c in groups.artist_counts.items() if c == n]
    if universal:
        name = groups.artist_names[universal[0]]
        msg = (
            f"Every selected entry is credited to {name}, so artist variety cannot be "
            "increased. Balanced ordering cannot separate them."
        )
        if strict:
            return result(
                [],
                ShuffleStatus.INFEASIBLE,
                notes=[msg, "Turn off strict mode to get a random order instead."],
            )
        order = fisher_yates(entries, rng)
        return result(
            order,
            ShuffleStatus.RELAXED,
            notes=[msg, "Used a uniform random order instead."],
            violations=_violations(order, gap, groups),
        )

    failures = _necessary_condition_failures(groups.artist_counts, n, gap)
    if failures:
        detail = "; ".join(
            f"{groups.artist_names[a]} has {c} of {n} entries (largest possible gap is {max(largest, 0)})"
            for a, c, largest in sorted(failures, key=lambda f: -f[1])[:5]
        )
        if strict:
            return result(
                [],
                ShuffleStatus.INFEASIBLE,
                notes=[
                    f"A gap of {gap} is impossible: {detail}.",
                    "Lower the gap, broaden the filter, or turn off strict mode.",
                ],
            )
        notes.append(f"A gap of {gap} cannot be met everywhere: {detail}.")

    attempts = 0
    if strict:
        plans = ["weighted"] * RANDOMIZED_ATTEMPTS + ["greedy"] * GREEDY_ATTEMPTS
        for policy in plans:
            attempts += 1
            try:
                order = _BalancedRun(groups, gap, rng, policy, allow_violations=False).run()
            except _DeadEnd:
                continue
            if policy == "greedy":
                notes.append("Used the deterministic most-remaining-first fallback.")
            return result(order, ShuffleStatus.OK, notes=notes, attempts=attempts)

        if n <= EXACT_SEARCH_MAX_ENTRIES:
            attempts += 1
            seq, exhausted = _exact_search(groups, gap, rng)
            if seq is not None:
                pools = [fisher_yates(m, rng) for m in groups.members]
                order = [pools[gi].pop() for gi in seq]
                notes.append("Found by exhaustive search after heuristic attempts failed.")
                return result(order, ShuffleStatus.OK, notes=notes, attempts=attempts)
            if exhausted:
                return result(
                    [],
                    ShuffleStatus.INFEASIBLE,
                    attempts=attempts,
                    notes=[
                        f"Exhaustive search proved no order satisfies a gap of {gap} for these "
                        "entries (collaborations make some artists collide).",
                        "Lower the gap or turn off strict mode.",
                    ],
                )
        return result(
            [],
            ShuffleStatus.NOT_FOUND,
            attempts=attempts,
            notes=[
                f"No order with a gap of {gap} was found within the search budget. One may "
                "still exist; the search is bounded to keep large playlists fast.",
                "Lower the gap or turn off strict mode to get the closest order with its violations listed.",
            ],
        )

    best: _BalancedRun | None = None
    best_order: list[PlaylistEntry] = []
    for _ in range(RELAXED_ATTEMPTS):
        attempts += 1
        exponent = WEIGHT_EXPONENT_OVERLOADED if failures else WEIGHT_EXPONENT
        run = _BalancedRun(groups, gap, rng, "weighted", allow_violations=True, exponent=exponent)
        order = run.run()
        if best is None or len(run.violations) < len(best.violations):
            best, best_order = run, order
        if not run.violations:
            break
    assert best is not None
    status = ShuffleStatus.OK if not best.violations else ShuffleStatus.RELAXED
    if best.violations:
        notes.append(f"{len(best.violations)} placements break the gap of {gap}; each one is listed.")
    return result(best_order, status, notes=notes, violations=best.violations, attempts=attempts)


def _violations(order: Sequence[PlaylistEntry], gap: int, groups: _Groups) -> list[Violation]:
    out: list[Violation] = []
    last: dict[str, int] = {}
    for pos, e in enumerate(order):
        keys = e.artist_keys()
        clash = [a for a in keys if a in last and pos - last[a] <= gap]
        if clash:
            out.append(
                Violation(
                    position=pos,
                    entry_id=e.entry_id,
                    conflicting_position=max(last[a] for a in clash),
                    shared_artists=tuple(sorted(groups.artist_names.get(a, a) for a in clash)),
                )
            )
        for a in keys:
            last[a] = pos
    return out


def find_violations(order: Sequence[PlaylistEntry], gap: int) -> list[Violation]:
    """Independent checker used by tests, metrics and the API response."""
    return _violations(order, gap, _Groups.build(order))


def shuffle(
    entries: Sequence[PlaylistEntry],
    mode: ShuffleMode,
    seed: int | None = None,
    minimum_artist_gap: int = 1,
    strict: bool = False,
    band_days: int = 30,
) -> ShuffleResult:
    if mode is ShuffleMode.RANDOM:
        return shuffle_random(entries, seed)
    if mode is ShuffleMode.RECENTLY_ADDED:
        return shuffle_recently_added(entries, seed, band_days)
    return shuffle_balanced(entries, seed, minimum_artist_gap, strict)
