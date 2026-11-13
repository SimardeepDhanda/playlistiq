"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { PlaylistSummary } from "@/lib/types";
import { useAuth } from "@/lib/useAuth";
import { SpotifyPlaylists } from "@/components/SpotifyPlaylists";

export default function Dashboard() {
  const [playlists, setPlaylists] = useState<PlaylistSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const auth = useAuth();

  useEffect(() => {
    api
      .playlists()
      .then((r) => setPlaylists(r.playlists))
      .catch((e: Error) => setError(e.message));
  }, []);

  const shown = useMemo(
    () => (playlists ?? []).filter((p) => p.name.toLowerCase().includes(query.trim().toLowerCase())),
    [playlists, query],
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Your playlists</h1>
          <p className="text-sm text-muted">
            {auth?.connected ? "Your Spotify playlists, plus demo playlists to experiment with." : "Demo playlists with synthetic songs."}
          </p>
        </div>
        <label className="flex flex-col text-sm">
          <span className="sr-only">Search playlists</span>
          <input
            type="search"
            placeholder="Search playlists"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-64 rounded-md border border-border bg-surface px-3 py-2"
          />
        </label>
      </div>

      {auth?.connected && <SpotifyPlaylists query={query} />}
      {auth?.connected && <h2 className="pt-4 text-lg font-semibold">Demo playlists</h2>}

      {error && (
        <p role="alert" className="rounded-md bg-danger-soft p-3 text-danger">
          Could not load playlists: {error}. Is the API running on port 8000?
        </p>
      )}
      {!playlists && !error && <p className="text-muted">Loading playlists…</p>}
      {playlists && shown.length === 0 && <p className="text-muted">No playlists match “{query}”.</p>}

      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {shown.map((p) => (
          <li key={p.id}>
            <Link
              href={`/playlist/${p.id}`}
              className="block h-full rounded-lg border border-border bg-surface p-5 hover:border-accent"
            >
              <div className="flex items-baseline justify-between gap-2">
                <h2 className="font-medium">{p.name}</h2>
                <span className="text-sm tabular-nums text-muted">{p.entry_count.toLocaleString()} songs</span>
              </div>
              <p className="mt-2 text-sm text-muted">{p.description}</p>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
