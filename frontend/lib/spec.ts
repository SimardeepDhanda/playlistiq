import type { QuerySpec } from "./types";

export type FilterState = "include" | "exclude" | null;
type Kind = "artist" | "album";

const keys = (kind: Kind) =>
  kind === "artist"
    ? (["include_artist_ids", "exclude_artist_ids"] as const)
    : (["include_album_ids", "exclude_album_ids"] as const);

export function stateOf(spec: QuerySpec, kind: Kind, id: string): FilterState {
  const [inc, exc] = keys(kind);
  if (spec[inc].includes(id)) return "include";
  if (spec[exc].includes(id)) return "exclude";
  return null;
}

/** Set one entity's state. An ID is never in both lists, so contradictions cannot be built in the UI. */
export function setState(spec: QuerySpec, kind: Kind, id: string, state: FilterState): QuerySpec {
  const [inc, exc] = keys(kind);
  const next = { ...spec, [inc]: spec[inc].filter((x) => x !== id), [exc]: spec[exc].filter((x) => x !== id) };
  if (state === "include") next[inc] = [...next[inc], id];
  if (state === "exclude") next[exc] = [...next[exc], id];
  return next;
}

export function hasFilters(spec: QuerySpec): boolean {
  return (
    spec.include_artist_ids.length +
      spec.exclude_artist_ids.length +
      spec.include_album_ids.length +
      spec.exclude_album_ids.length >
    0
  );
}

export function randomSeed(): number {
  return Math.floor(Math.random() * Number.MAX_SAFE_INTEGER);
}
