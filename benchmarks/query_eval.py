"""Measure the deterministic query parser against the hand-labeled query set.

Usage (from the repository root):
    cd backend && uv run python ../benchmarks/query_eval.py [--json out.json] [--show-failures]

Reports exact structured-parse accuracy and entry-selection precision/recall
on the synthetic demo playlist. Nothing here is estimated: every number comes
from running the parser.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.engine.filters import apply_filters  # noqa: E402
from app.engine.models import PlaylistEntry, QuerySpec  # noqa: E402
from app.engine.query_parser import Catalog, DeterministicQueryParser  # noqa: E402
from app.services.demo import load_demo_playlists  # noqa: E402

LABELS = ROOT / "benchmarks" / "query_labels.json"
HOLDOUT = ROOT / "benchmarks" / "query_labels_holdout.json"
FLAGS = ("ambiguous", "unsupported", "unrecognized", "contradiction")


def _resolver(entries: tuple[PlaylistEntry, ...]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    artists: dict[str, set[str]] = {}
    albums: dict[str, set[str]] = {}
    for e in entries:
        for a in e.artists:
            artists.setdefault(a.name, set()).add(a.key)
        if e.album and e.album.name and e.album.key:
            albums.setdefault(e.album.name, set()).add(e.album.key)
            owner = (e.album.artists or e.artists[:1])[0].name if (e.album.artists or e.artists) else ""
            albums.setdefault(f"{e.album.name}@{owner}", set()).add(e.album.key)
    return artists, albums


def expected_spec(
    label: dict[str, Any], artists: dict[str, set[str]], albums: dict[str, set[str]]
) -> QuerySpec:
    def ids(names: list[str], table: dict[str, set[str]]) -> list[str]:
        out: list[str] = []
        for n in names:
            if n not in table:
                raise KeyError(f"label refers to unknown name {n!r}")
            out.extend(sorted(table[n]))
        return out

    return QuerySpec(
        include_artist_ids=ids(label.get("include_artists", []), artists),
        exclude_artist_ids=ids(label.get("exclude_artists", []), artists),
        include_album_ids=ids(label.get("include_albums", []), albums),
        exclude_album_ids=ids(label.get("exclude_albums", []), albums),
        shuffle_mode=label.get("shuffle_mode", "balanced"),
        minimum_artist_gap=label.get("minimum_artist_gap", 1),
        strict_constraints=label.get("strict_constraints", False),
        seed=label.get("seed"),
        primary_artist_only=label.get("primary_artist_only", False),
    )


def comparable(spec: QuerySpec) -> dict[str, Any]:
    d = spec.model_dump()
    for k in ("include_artist_ids", "exclude_artist_ids", "include_album_ids", "exclude_album_ids"):
        d[k] = sorted(set(d[k]))
    return d


def evaluate(labels: Path = LABELS) -> dict[str, Any]:
    data = json.loads(labels.read_text())
    playlist = load_demo_playlists(get_settings().demo_data_path)[data["playlist_id"]]
    catalog = Catalog.from_entries(playlist.entries)
    artists, albums = _resolver(playlist.entries)
    parser = DeterministicQueryParser()

    exact = 0
    tp = fp = fn = 0
    rows = []
    for label in data["queries"]:
        result = parser.parse(label["query"], catalog)
        got_flags = {
            "ambiguous": bool(result.ambiguities),
            "unsupported": bool(result.unsupported),
            "unrecognized": bool(result.unrecognized),
            "contradiction": bool(result.contradictions),
        }
        want_flags = {f: f in label.get("expect", []) for f in FLAGS}
        clarify = want_flags["ambiguous"] or want_flags["contradiction"]
        want = None if clarify else expected_spec(label, artists, albums)

        spec_ok = (
            result.spec is None
            if want is None
            else result.spec is not None and comparable(result.spec) == comparable(want)
        )
        ok = spec_ok and got_flags == want_flags
        exact += ok

        if want is not None:
            want_ids = {e.entry_id for e in apply_filters(playlist.entries, want).matched}
            got_ids = (
                {e.entry_id for e in apply_filters(playlist.entries, result.spec).matched}
                if result.spec is not None and not result.ambiguities
                else set()
            )
            tp += len(want_ids & got_ids)
            fp += len(got_ids - want_ids)
            fn += len(want_ids - got_ids)
        rows.append(
            {
                "query": label["query"],
                "ok": ok,
                "spec_ok": spec_ok,
                "flags_expected": [f for f, v in want_flags.items() if v],
                "flags_got": [f for f, v in got_flags.items() if v],
                "unrecognized": result.unrecognized,
            }
        )

    n = len(data["queries"])
    return {
        "queries": n,
        "exact_parse_accuracy": round(exact / n, 4),
        "exact_matches": exact,
        "selection_precision": round(tp / (tp + fp), 4) if tp + fp else 1.0,
        "selection_recall": round(tp / (tp + fn), 4) if tp + fn else 1.0,
        "rows": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path)
    ap.add_argument("--show-failures", action="store_true")
    ap.add_argument("--holdout", action="store_true", help="use the held-out query set")
    args = ap.parse_args()
    report = evaluate(HOLDOUT if args.holdout else LABELS)
    print(f"queries:               {report['queries']}")
    print(
        f"exact parse accuracy:  {report['exact_parse_accuracy']:.1%} "
        f"({report['exact_matches']}/{report['queries']})"
    )
    print(f"selection precision:   {report['selection_precision']:.1%}")
    print(f"selection recall:      {report['selection_recall']:.1%}")
    if args.show_failures:
        for r in report["rows"]:
            if not r["ok"]:
                print(
                    f"  FAIL {r['query']!r}: spec_ok={r['spec_ok']} "
                    f"flags want={r['flags_expected']} got={r['flags_got']} "
                    f"unrecognized={r['unrecognized']}"
                )
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
