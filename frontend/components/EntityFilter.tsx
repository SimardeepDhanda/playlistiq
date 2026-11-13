"use client";

import { useId, useMemo, useState } from "react";
import type { FilterState } from "@/lib/spec";

export interface EntityRow {
  id: string;
  name: string;
  detail?: string;
  count: number;
}

interface Props {
  label: string;
  rows: EntityRow[];
  stateOf: (id: string) => FilterState;
  onChange: (id: string, state: FilterState) => void;
  limit?: number;
}

/** Searchable list where each artist or album can be included, excluded, or left alone. */
export function EntityFilter({ label, rows, stateOf, onChange, limit = 8 }: Props) {
  const [query, setQuery] = useState("");
  const searchId = useId();
  const selected = rows.filter((r) => stateOf(r.id) !== null);
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q ? rows.filter((r) => r.name.toLowerCase().includes(q)) : rows;
    return list.slice(0, limit);
  }, [rows, query, limit]);

  return (
    <fieldset className="min-w-0 space-y-2">
      <legend className="text-sm font-medium">{label}</legend>

      {selected.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label={`Selected ${label.toLowerCase()}`}>
          {selected.map((r) => {
            const s = stateOf(r.id);
            return (
              <li
                key={r.id}
                className={`flex items-center gap-1 rounded-full px-3 py-1 text-xs ${
                  s === "include" ? "bg-accent-soft text-accent" : "bg-danger-soft text-danger"
                }`}
              >
                <span>
                  {s === "include" ? "Only" : "Not"} {r.name}
                  {r.detail ? ` (${r.detail})` : ""}
                </span>
                <button
                  type="button"
                  onClick={() => onChange(r.id, null)}
                  aria-label={`Remove rule for ${r.name}`}
                  className="ml-1 font-bold"
                >
                  ×
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <label htmlFor={searchId} className="sr-only">
        Search {label.toLowerCase()}
      </label>
      <input
        id={searchId}
        type="search"
        placeholder={`Search ${label.toLowerCase()}`}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="w-full rounded-md border border-border bg-surface px-3 py-1.5 text-sm"
      />
      <ul className="divide-y divide-border rounded-md border border-border bg-surface">
        {matches.length === 0 && <li className="px-3 py-2 text-sm text-muted">No matches in this playlist.</li>}
        {matches.map((r) => {
          const s = stateOf(r.id);
          return (
            <li key={r.id} className="flex items-center gap-2 px-3 py-1.5 text-sm">
              <span className="min-w-0 flex-1 truncate" title={r.detail ? `${r.name} (${r.detail})` : r.name}>
                {r.name}
                {r.detail && <span className="text-muted"> · {r.detail}</span>}
              </span>
              <span className="tabular-nums text-xs text-muted">{r.count}</span>
              <button
                type="button"
                aria-pressed={s === "include"}
                aria-label={`Include ${r.name}${r.detail ? ` (${r.detail})` : ""}`}
                onClick={() => onChange(r.id, s === "include" ? null : "include")}
                className={`rounded px-2 py-0.5 text-xs ${
                  s === "include" ? "bg-accent text-white dark:text-black" : "border border-border"
                }`}
              >
                Only
              </button>
              <button
                type="button"
                aria-pressed={s === "exclude"}
                aria-label={`Exclude ${r.name}${r.detail ? ` (${r.detail})` : ""}`}
                onClick={() => onChange(r.id, s === "exclude" ? null : "exclude")}
                className={`rounded px-2 py-0.5 text-xs ${
                  s === "exclude" ? "bg-danger text-white dark:text-black" : "border border-border"
                }`}
              >
                Not
              </button>
            </li>
          );
        })}
      </ul>
    </fieldset>
  );
}
