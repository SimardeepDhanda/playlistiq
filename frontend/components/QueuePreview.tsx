"use client";

import { useState } from "react";
import type { PreviewResponse } from "@/lib/types";

const STATUS: Record<PreviewResponse["status"], { label: string; tone: string }> = {
  ok: { label: "All rules met", tone: "bg-accent-soft text-accent" },
  relaxed: { label: "Spacing not fully met", tone: "bg-warn-soft text-warn" },
  infeasible: { label: "Impossible with these rules", tone: "bg-danger-soft text-danger" },
  not_found: { label: "No valid order found", tone: "bg-danger-soft text-danger" },
};

const PAGE = 100;

function duration(ms: number | null): string {
  if (!ms) return "";
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function QueuePreview({ preview }: { preview: PreviewResponse }) {
  const [shown, setShown] = useState(PAGE);
  const status = STATUS[preview.status];
  const brokenAt = new Map(preview.violations.map((v) => [v.position, v]));

  return (
    <section aria-labelledby="preview-heading" className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="preview-heading" className="text-lg font-semibold">
          <span data-testid="match-count">{preview.match_count.toLocaleString()}</span> of{" "}
          {preview.total_entries.toLocaleString()} songs match
        </h2>
        <span className={`rounded-full px-3 py-1 text-xs font-medium ${status.tone}`} data-testid="status">
          {status.label}
        </span>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-md border border-border bg-surface p-3 text-sm">
          <h3 className="mb-1 font-medium">Rules applied</h3>
          <ul className="list-disc space-y-0.5 pl-5" data-testid="rules">
            {preview.applied_rules.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          <p className="mt-2 break-all text-xs text-muted">
            Seed {preview.seed}. The same seed and rules always give the same order.
          </p>
        </div>
        <div className="rounded-md border border-border bg-surface p-3 text-sm">
          <h3 className="mb-1 font-medium">About this order</h3>
          <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5 text-xs">
            <dt className="text-muted">Neighbours sharing an artist</dt>
            <dd className="tabular-nums">{(preview.metrics.adjacent_overlap_rate * 100).toFixed(1)}%</dd>
            <dt className="text-muted">Same-artist pairs within 3 songs</dt>
            <dd className="tabular-nums">{preview.metrics.same_artist_pairs_within_3}</dd>
            <dt className="text-muted">Spacing breaks</dt>
            <dd className="tabular-nums">{preview.violations.length}</dd>
            <dt className="text-muted">Engine time</dt>
            <dd className="tabular-nums">{preview.timing.total_ms.toFixed(1)} ms</dd>
          </dl>
        </div>
      </div>

      {preview.notes.length > 0 && (
        <ul className="space-y-1 text-sm" data-testid="notes">
          {preview.notes.map((n) => (
            <li key={n} className="rounded-md bg-surface-2 px-3 py-2">
              {n}
            </li>
          ))}
        </ul>
      )}

      {preview.queue.length > 0 && (
        <ol className="divide-y divide-border rounded-md border border-border bg-surface" data-testid="queue">
          {preview.queue.slice(0, shown).map((q) => {
            const broken = brokenAt.get(q.queue_position);
            return (
              <li key={q.entry_id} className="flex items-center gap-3 px-3 py-2 text-sm">
                <span className="w-10 shrink-0 text-right tabular-nums text-muted">{q.queue_position + 1}</span>
                <div className="min-w-0 flex-1">
                  <p className="truncate">
                    {q.name}
                    {q.is_local && <span className="ml-2 text-xs text-muted">(local file)</span>}
                    {q.is_playable === false && !q.is_local && (
                      <span className="ml-2 text-xs text-muted">(unavailable)</span>
                    )}
                  </p>
                  <p className="truncate text-xs text-muted">
                    {q.artists.map((a) => a.name).join(", ") || "Unknown artist"}
                    {q.album?.name ? ` · ${q.album.name}` : ""}
                  </p>
                </div>
                {broken && (
                  <span
                    className="shrink-0 rounded bg-warn-soft px-2 py-0.5 text-xs text-warn"
                    title={`Shares ${broken.shared_artists.join(", ")} with song ${broken.conflicting_position + 1}`}
                  >
                    close to #{broken.conflicting_position + 1}
                  </span>
                )}
                <span className="shrink-0 tabular-nums text-xs text-muted">{duration(q.duration_ms)}</span>
              </li>
            );
          })}
        </ol>
      )}
      {preview.queue.length > shown && (
        <button
          type="button"
          onClick={() => setShown(shown + PAGE * 5)}
          className="rounded-md border border-border px-4 py-2 text-sm"
        >
          Show more ({(preview.queue.length - shown).toLocaleString()} left)
        </button>
      )}
    </section>
  );
}
