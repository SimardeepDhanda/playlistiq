"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { SpotifyPlaylist } from "@/lib/types";

export function SpotifyPlaylists({ query }: { query: string }) {
  const [rows, setRows] = useState<SpotifyPlaylist[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    api
      .spotifyPlaylists()
      .then(setRows)
      .catch((e: Error) => setError(e.message));
  }, []);

  async function importOne(p: SpotifyPlaylist) {
    setBusy(p.id);
    setError(null);
    setMessage(null);
    try {
      const r = await api.sync(p.id);
      const skipped = r.skipped_unavailable + r.skipped_episodes;
      setMessage(
        `Imported ${r.entry_count.toLocaleString()} songs from “${r.name}”` +
          (skipped ? ` (${skipped} unavailable items or podcast episodes skipped).` : "."),
      );
      setRows((rs) => rs?.map((x) => (x.id === p.id ? { ...x, imported: true } : x)) ?? null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const shown = (rows ?? []).filter((p) => p.name.toLowerCase().includes(query.trim().toLowerCase()));

  return (
    <section className="space-y-3" aria-labelledby="spotify-heading">
      <h2 id="spotify-heading" className="text-lg font-semibold">
        Your Spotify playlists
      </h2>
      <p className="text-sm text-muted">
        Spotify only lets this app read songs from playlists you own or collaborate on. Importing reads every song once
        and keeps a private copy for 24 hours.
      </p>
      {error && (
        <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
          {error}
        </p>
      )}
      {message && (
        <p role="status" className="rounded-md bg-accent-soft p-3 text-sm text-accent">
          {message}
        </p>
      )}
      {!rows && !error && <p className="text-sm text-muted">Loading your playlists from Spotify…</p>}
      {rows && shown.length === 0 && <p className="text-sm text-muted">No playlists to show.</p>}
      <ul className="divide-y divide-border rounded-lg border border-border bg-surface">
        {shown.map((p) => (
          <li key={p.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{p.name}</p>
              <p className="text-xs text-muted">
                {p.item_count != null ? `${p.item_count.toLocaleString()} items` : "Item count unknown"}
                {p.owner_name ? ` · by ${p.owner_name}` : ""}
              </p>
            </div>
            {!p.readable ? (
              <span className="text-xs text-muted">Not yours, so Spotify won’t share its songs</span>
            ) : (
              <>
                {p.imported && (
                  <Link
                    href={`/playlist/${p.id}`}
                    className="rounded-md bg-accent px-3 py-1.5 text-sm text-white dark:text-black"
                  >
                    Open
                  </Link>
                )}
                <button
                  type="button"
                  onClick={() => importOne(p)}
                  disabled={busy !== null}
                  className="rounded-md border border-border px-3 py-1.5 text-sm disabled:opacity-50"
                >
                  {busy === p.id ? "Importing…" : p.imported ? "Refresh" : "Import"}
                </button>
              </>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
