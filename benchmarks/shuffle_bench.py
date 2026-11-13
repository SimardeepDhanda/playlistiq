"""Benchmark the ordering engines on synthetic playlists.

Usage (from the repository root):
    cd backend && uv run python ../benchmarks/shuffle_bench.py [--quick] [--out ../docs/benchmarks.md]

Everything printed is measured by running the code on this machine. Timings
cover the engine only (no HTTP, no network). Memory is the Python heap peak
reported by tracemalloc during one run.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
import tracemalloc
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from random import Random
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.engine.metrics import (  # noqa: E402
    adjacent_overlap_rate,
    is_valid_permutation,
    positional_agreement,
    same_artist_pairs_within,
)
from app.engine.models import Album, Artist, PlaylistEntry, ShuffleMode  # noqa: E402
from app.engine.shuffle import find_violations, shuffle  # noqa: E402

SIZES = [100, 500, 2_000, 5_000, 10_000]


def synthetic(n: int, profile: str, seed: int = 0) -> list[PlaylistEntry]:
    """Synthetic playlist with a chosen artist distribution.

    * ``spread``: Zipf-like counts over n/8 artists (typical large playlist).
    * ``skewed``: one artist holds 25% of entries, the rest Zipf-like.
    * ``collab``: like spread, but 15% of entries credit two artists.
    """
    rng = Random(seed)
    n_artists = max(4, n // 8)
    weights = [1 / (r + 1) ** 0.9 for r in range(n_artists)]
    artists = [Artist(id=f"a{i}", name=f"Artist {i}") for i in range(n_artists)]
    entries = []
    for pos in range(n):
        if profile == "skewed" and rng.random() < 0.25:
            credited = (artists[0],)
        else:
            lead = rng.choices(artists[1:], weights=weights[1:])[0]
            credited = (lead,)
            if profile == "collab" and rng.random() < 0.15:
                guest = rng.choices(artists, weights=weights)[0]
                if guest != lead:
                    credited = (lead, guest)
        entries.append(
            PlaylistEntry(
                entry_id=f"bench:{pos}",
                playlist_id="bench",
                position=pos,
                track_id=f"t{pos}",
                uri=f"demo:track:t{pos}",
                name=f"Track {pos}",
                artists=credited,
                album=Album(id=f"al{pos % 97}", name=f"Album {pos % 97}"),
                added_at=datetime(2024, 1, 1, tzinfo=UTC).replace(day=1 + pos % 28),
            )
        )
    return entries


def time_run(
    entries: list[PlaylistEntry], mode: ShuffleMode, gap: int, strict: bool, repeats: int
) -> dict[str, Any]:
    times = []
    result = None
    for r in range(repeats):
        t0 = time.perf_counter()
        result = shuffle(entries, mode, seed=r, minimum_artist_gap=gap, strict=strict)
        times.append((time.perf_counter() - t0) * 1000)
    assert result is not None
    tracemalloc.start()
    shuffle(entries, mode, seed=0, minimum_artist_gap=gap, strict=strict)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    order = result.order
    valid = is_valid_permutation(entries, order) if order else None
    return {
        "median_ms": round(statistics.median(times), 2),
        "max_ms": round(max(times), 2),
        "peak_kib": round(peak / 1024, 1),
        "status": result.status.value,
        "valid_permutation": valid,
        "adjacent_overlap": round(adjacent_overlap_rate(order), 4) if order else None,
        "pairs_within_3": same_artist_pairs_within(order, 3) if order else None,
        "pairs_within_5": same_artist_pairs_within(order, 5) if order else None,
        "gap_violations": len(find_violations(order, gap)) if order else None,
    }


def diversity(entries: list[PlaylistEntry], mode: ShuffleMode, gap: int, seeds: int) -> float:
    orders = [shuffle(entries, mode, seed=s, minimum_artist_gap=gap).order for s in range(seeds)]
    pairs = [positional_agreement(orders[i], orders[i + 1]) for i in range(seeds - 1)]
    return round(statistics.mean(pairs), 5)


def fairness(n: int, runs: int) -> dict[str, Any]:
    """Run ``runs`` seeds on a small skewed playlist and look at where the
    dominant artist lands. A fair order puts its mean position near 0.5 and
    spreads it evenly over the first, middle and last thirds."""
    entries = synthetic(n, "skewed", seed=11)
    dominant = "a0"
    out: dict[str, Any] = {
        "entries": n,
        "runs": runs,
        "dominant_share": sum(dominant in e.artist_keys() for e in entries) / n,
    }
    for mode, gap in ((ShuffleMode.RANDOM, 0), (ShuffleMode.BALANCED, 1), (ShuffleMode.BALANCED, 2)):
        thirds = [0, 0, 0]
        pos_sum = 0.0
        hits = 0
        adj = []
        for s in range(runs):
            order = shuffle(entries, mode, seed=s, minimum_artist_gap=gap).order
            adj.append(adjacent_overlap_rate(order))
            for p, e in enumerate(order):
                if dominant in e.artist_keys():
                    pos_sum += p / (n - 1)
                    thirds[min(2, 3 * p // n)] += 1
                    hits += 1
        label = f"{mode.value}" + (f" gap {gap}" if mode is ShuffleMode.BALANCED else "")
        out[label] = {
            "dominant_mean_position": round(pos_sum / hits, 4),
            "dominant_share_by_third": [round(t / hits, 4) for t in thirds],
            "adjacent_overlap_mean": round(statistics.mean(adj), 4),
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="fewer repeats, for CI")
    ap.add_argument("--out", type=Path, help="write a Markdown report here")
    ap.add_argument("--json", type=Path, help="write raw results here")
    args = ap.parse_args()
    repeats = 3 if args.quick else 7
    fairness_runs = 1_000 if args.quick else 10_000

    configs = [
        ("random", ShuffleMode.RANDOM, 0, False),
        ("balanced gap 1", ShuffleMode.BALANCED, 1, False),
        ("balanced gap 3", ShuffleMode.BALANCED, 3, False),
        ("balanced gap 3 strict", ShuffleMode.BALANCED, 3, True),
        ("recently added", ShuffleMode.RECENTLY_ADDED, 0, False),
    ]
    rows: list[dict[str, Any]] = []
    for profile in ("spread", "skewed", "collab"):
        for n in SIZES:
            entries = synthetic(n, profile)
            for label, mode, gap, strict in configs:
                r = time_run(entries, mode, gap, strict, repeats)
                rows.append({"profile": profile, "entries": n, "config": label, **r})
                print(
                    f"{profile:7} {n:>6} {label:22} {r['median_ms']:>9.2f} ms  "
                    f"{r['status']:10} adj={r['adjacent_overlap']} viol={r['gap_violations']}",
                    flush=True,
                )

    div = {
        label: diversity(synthetic(2_000, "spread"), mode, gap, 10)
        for label, mode, gap, _ in configs
        if mode is not ShuffleMode.RECENTLY_ADDED
    }
    fair = fairness(40, fairness_runs)
    meta = {
        "measured_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "repeats": repeats,
    }
    report = {"meta": meta, "rows": rows, "diversity": div, "fairness": fair}
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n")
    if args.out:
        args.out.write_text(render(report))
    print(json.dumps({"diversity": div, "fairness": fair}, indent=2))


def render(report: dict[str, Any]) -> str:
    m = report["meta"]
    lines = [
        "# Shuffle benchmarks",
        "",
        f"Measured {m['measured_at']} on {m['platform']} ({m['processor']}), "
        f"Python {m['python']}. Median of {m['repeats']} runs per cell, engine only "
        "(no HTTP or network). Generated by `benchmarks/shuffle_bench.py`; rerun it to "
        "refresh these numbers on your machine.",
        "",
        "Profiles: **spread** has Zipf-like artist counts over n/8 artists; **skewed** gives "
        "one artist 25% of entries; **collab** credits two artists on 15% of entries.",
        "",
        "`adj` is the share of neighbouring pairs that share an artist. `viol` counts "
        "placements that break the requested gap (random and recently added are checked "
        "against gap 0, so they show 0).",
        "",
    ]
    by_profile: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in report["rows"]:
        by_profile[r["profile"]].append(r)
    for profile, rows in by_profile.items():
        lines += [
            f"## {profile}",
            "",
            "| entries | config | median ms | peak KiB | status | adj | within 3 | viol |",
            "|---:|---|---:|---:|---|---:|---:|---:|",
        ]
        for r in rows:
            lines.append(
                f"| {r['entries']:,} | {r['config']} | {r['median_ms']} | {r['peak_kib']} | "
                f"{r['status']} | {_fmt(r['adjacent_overlap'])} | {_fmt(r['pairs_within_3'])} | "
                f"{_fmt(r['gap_violations'])} |"
            )
        lines.append("")
    lines += [
        "## Diversity across seeds",
        "",
        "Mean share of positions holding the same entry for consecutive seeds on a "
        "2,000-entry spread playlist (independent uniform shuffles give about 1/2000 = "
        "0.0005).",
        "",
        "| config | positional agreement |",
        "|---|---:|",
    ]
    lines += [f"| {k} | {v} |" for k, v in report["diversity"].items()]
    f = report["fairness"]
    lines += [
        "",
        "## Position fairness",
        "",
        f"{f['runs']:,} seeds on a {f['entries']}-entry skewed playlist where one artist "
        f"holds {f['dominant_share']:.0%} of entries. A fair order puts that artist's mean "
        "position near 0.5. The thirds hold 14, 13 and 13 slots, so a uniform order gives "
        "about 0.350 / 0.325 / 0.325.",
        "",
        "| config | mean position | share in first / middle / last third | adj mean |",
        "|---|---:|---|---:|",
    ]
    for k, v in f.items():
        if isinstance(v, dict):
            thirds = " / ".join(f"{x:.3f}" for x in v["dominant_share_by_third"])
            lines.append(f"| {k} | {v['dominant_mean_position']} | {thirds} | {v['adjacent_overlap_mean']} |")
    lines.append("")
    return "\n".join(lines)


def _fmt(v: object) -> str:
    return "n/a" if v is None else str(v)


if __name__ == "__main__":
    main()
