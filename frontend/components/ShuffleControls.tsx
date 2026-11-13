"use client";

import type { QuerySpec, ShuffleMode } from "@/lib/types";
import { randomSeed } from "@/lib/spec";

const MODES: { value: ShuffleMode; label: string; help: string }[] = [
  { value: "balanced", label: "Balanced", help: "Random, but keeps the same artist apart." },
  { value: "random", label: "True random", help: "Every order is equally likely (Fisher-Yates)." },
  { value: "recently_added", label: "Recently added", help: "Newest additions first. Not a uniform shuffle." },
];

interface Props {
  spec: QuerySpec;
  onChange: (spec: QuerySpec) => void;
}

export function ShuffleControls({ spec, onChange }: Props) {
  return (
    <fieldset className="min-w-0 space-y-3">
      <legend className="text-sm font-medium">Order</legend>
      <div role="radiogroup" aria-label="Shuffle mode" className="space-y-1">
        {MODES.map((m) => (
          <label key={m.value} className="flex cursor-pointer items-start gap-2 text-sm">
            <input
              type="radio"
              name="mode"
              value={m.value}
              checked={spec.shuffle_mode === m.value}
              onChange={() => onChange({ ...spec, shuffle_mode: m.value })}
              className="mt-1"
            />
            <span>
              {m.label}
              <span className="block text-xs text-muted">{m.help}</span>
            </span>
          </label>
        ))}
      </div>

      {spec.shuffle_mode === "balanced" && (
        <div className="space-y-2 rounded-md bg-surface-2 p-3">
          <label className="flex items-center justify-between gap-2 text-sm">
            <span>Songs between the same artist</span>
            <input
              type="number"
              min={0}
              max={50}
              value={spec.minimum_artist_gap}
              onChange={(e) =>
                onChange({ ...spec, minimum_artist_gap: Math.max(0, Math.min(50, Number(e.target.value) || 0)) })
              }
              className="w-16 rounded border border-border bg-surface px-2 py-1 text-right"
            />
          </label>
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={spec.strict_constraints}
              onChange={(e) => onChange({ ...spec, strict_constraints: e.target.checked })}
              className="mt-1"
            />
            <span>
              Strict
              <span className="block text-xs text-muted">
                Refuse to build an order that breaks the spacing. Off: get the closest order, with every break listed.
              </span>
            </span>
          </label>
        </div>
      )}

      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={spec.primary_artist_only}
          onChange={(e) => onChange({ ...spec, primary_artist_only: e.target.checked })}
          className="mt-1"
        />
        <span>
          Match the main artist only
          <span className="block text-xs text-muted">By default a song matches if any credited artist matches.</span>
        </span>
      </label>

      <div className="flex items-center gap-2 text-sm">
        <label htmlFor="seed">Seed</label>
        <input
          id="seed"
          inputMode="numeric"
          placeholder="random"
          value={spec.seed ?? ""}
          onChange={(e) => {
            const v = e.target.value.replace(/\D/g, "").slice(0, 15);
            onChange({ ...spec, seed: v ? Number(v) : null });
          }}
          className="w-32 rounded border border-border bg-surface px-2 py-1"
        />
        <button
          type="button"
          onClick={() => onChange({ ...spec, seed: randomSeed() })}
          className="rounded border border-border px-2 py-1 text-xs"
        >
          New seed
        </button>
      </div>
    </fieldset>
  );
}
