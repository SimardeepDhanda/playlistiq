"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ExportStatus, PreviewResponse } from "@/lib/types";

interface Props {
  preview: PreviewResponse;
  playlistName: string;
  live: boolean;
}

function newKey(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

export function ExportPanel({ preview, playlistName, live }: Props) {
  const count = preview.queue.length;
  const exportable = preview.queue.filter((q) => q.uri?.startsWith("spotify:track:") && !q.is_local).length;
  const [name, setName] = useState(`${playlistName} · PlaylistIQ mix`.slice(0, 100));
  const [confirming, setConfirming] = useState(false);
  const [job, setJob] = useState<ExportStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  // One idempotency key per previewed order (the parent remounts this panel for
  // each new preview): double clicks and retries reuse it.
  const [key] = useState(newKey);

  useEffect(() => {
    if (!job || job.status === "completed" || job.status === "failed") return;
    const t = setTimeout(() => {
      api.getExport(job.id).then(setJob).catch((e: Error) => setError(e.message));
    }, 1000);
    return () => clearTimeout(t);
  }, [job]);

  if (!live) {
    return (
      <div className="space-y-2 rounded-md border border-border bg-surface p-3 text-sm">
        <h3 className="font-medium">Save as a new Spotify playlist</h3>
        <p className="text-muted">
          Export creates a <strong>new</strong> playlist in this exact order ({count.toLocaleString()} songs) and never
          touches the original. Turn Spotify&apos;s own shuffle off when you play it.
        </p>
        <button type="button" disabled aria-describedby="export-why" className="rounded-md border border-border px-4 py-2 text-muted">
          Export to Spotify
        </button>
        <p id="export-why" className="text-xs text-muted">
          Not available for demo playlists: these songs are synthetic. Connect Spotify and import one of your own
          playlists to export.
        </p>
      </div>
    );
  }

  async function start() {
    setError(null);
    try {
      setJob(await api.startExport(key, { playlist_id: preview.playlist_id, spec: preview.spec, name }));
      setConfirming(false);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function retry() {
    if (!job) return;
    setError(null);
    try {
      setJob(await api.retryExport(job.id));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const pct = job && job.total_items ? Math.round((100 * job.completed_items) / job.total_items) : 0;

  return (
    <div className="space-y-3 rounded-md border border-border bg-surface p-4 text-sm" data-testid="export">
      <h3 className="font-medium">Save as a new Spotify playlist</h3>
      {!job && !confirming && (
        <>
          <label className="block space-y-1">
            <span>Name</span>
            <input
              value={name}
              maxLength={100}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-md border border-border bg-surface px-3 py-2"
            />
          </label>
          <button
            type="button"
            disabled={!name.trim() || exportable === 0}
            onClick={() => setConfirming(true)}
            className="rounded-md bg-accent px-4 py-2 font-medium text-white disabled:opacity-50 dark:text-black"
          >
            Export to Spotify
          </button>
          {exportable < count && (
            <p className="text-xs text-muted">
              {count - exportable} local files or unavailable items cannot be added through Spotify and will be skipped.
            </p>
          )}
        </>
      )}

      {confirming && !job && (
        <div role="alertdialog" aria-labelledby="confirm-title" className="space-y-3 rounded-md bg-surface-2 p-3">
          <p id="confirm-title" className="font-medium">
            Create a new private playlist “{name}” with {exportable.toLocaleString()} songs?
          </p>
          <p className="text-muted">Your original playlist stays exactly as it is.</p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={start}
              className="rounded-md bg-accent px-4 py-2 font-medium text-white dark:text-black"
            >
              Create playlist
            </button>
            <button type="button" onClick={() => setConfirming(false)} className="rounded-md border border-border px-4 py-2">
              Cancel
            </button>
          </div>
        </div>
      )}

      {job && (
        <div className="space-y-2" aria-live="polite">
          <div
            className="h-2 overflow-hidden rounded bg-surface-2"
            role="progressbar"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Export progress"
          >
            <div className="h-full bg-accent transition-all" style={{ width: `${pct}%` }} />
          </div>
          <p>
            {job.status === "completed"
              ? `Done: ${job.total_items.toLocaleString()} songs added in order and checked.`
              : job.status === "failed"
                ? `Stopped after ${job.completed_items.toLocaleString()} of ${job.total_items.toLocaleString()} songs.`
                : `Adding songs… ${job.completed_items.toLocaleString()} of ${job.total_items.toLocaleString()}`}
          </p>
          {job.error && <p className="text-danger">{job.error}</p>}
          {job.status === "failed" && (
            <button type="button" onClick={retry} className="rounded-md border border-border px-4 py-2">
              Retry (continues the same playlist)
            </button>
          )}
          {job.destination_url && (
            <a href={job.destination_url} target="_blank" rel="noreferrer" className="text-accent underline">
              Open in Spotify
            </a>
          )}
          {job.status === "completed" && (
            <p className="text-xs text-muted">Turn Spotify&apos;s shuffle off so it plays in this order.</p>
          )}
        </div>
      )}
      {error && (
        <p role="alert" className="text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
