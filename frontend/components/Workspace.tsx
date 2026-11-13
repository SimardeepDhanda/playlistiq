"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { hasFilters, setState, stateOf } from "@/lib/spec";
import { DEFAULT_SPEC, type EntityOption, type Facets, type ParseResult, type PreviewResponse, type QuerySpec } from "@/lib/types";
import { EntityFilter } from "./EntityFilter";
import { ExportPanel } from "./ExportPanel";
import { QueryBox } from "./QueryBox";
import { QueuePreview } from "./QueuePreview";
import { ShuffleControls } from "./ShuffleControls";

export function Workspace({ playlistId }: { playlistId: string }) {
  const [facets, setFacets] = useState<Facets | null>(null);
  const [spec, setSpec] = useState<QuerySpec>(DEFAULT_SPEC);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [previewVersion, setPreviewVersion] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [playlistName, setPlaylistName] = useState<string>("");
  const [needsImport, setNeedsImport] = useState(false);
  const [importing, setImporting] = useState(false);
  const live = !playlistId.startsWith("demo-");

  const loadFacets = useCallback(() => {
    api
      .facets(playlistId)
      .then(setFacets)
      .catch((e: Error) => {
        if (e instanceof ApiError && e.status === 409) setNeedsImport(true);
        else if (e instanceof ApiError && e.status === 404 && live)
          setError("Connect Spotify and import this playlist to use it.");
        else setError(e.message);
      });
  }, [playlistId, live]);

  useEffect(() => {
    loadFacets();
    if (live) {
      api
        .spotifyPlaylists()
        .then((r) => setPlaylistName(r.find((p) => p.id === playlistId)?.name ?? "Spotify playlist"))
        .catch(() => setPlaylistName("Spotify playlist"));
    } else {
      api
        .playlists()
        .then((r) => setPlaylistName(r.playlists.find((p) => p.id === playlistId)?.name ?? playlistId))
        .catch(() => setPlaylistName(playlistId));
    }
  }, [playlistId, live, loadFacets]);

  async function importNow() {
    setImporting(true);
    setError(null);
    try {
      await api.sync(playlistId);
      setNeedsImport(false);
      loadFacets();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setImporting(false);
    }
  }

  const artistRows = useMemo(
    () =>
      (facets?.artists ?? []).map((a) => ({
        id: a.id,
        name: a.name,
        count: a.entry_count,
        detail: a.detail || undefined,
      })),
    [facets],
  );
  const albumRows = useMemo(
    () => (facets?.albums ?? []).map((a) => ({ id: a.id, name: a.name, detail: a.artist_names, count: a.entry_count })),
    [facets],
  );

  const run = useCallback(
    async (s: QuerySpec) => {
      setLoading(true);
      setError(null);
      try {
        const p = await api.preview(playlistId, s);
        setPreview(p);
        setPreviewVersion((v) => v + 1);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    },
    [playlistId],
  );

  function applyParsed(r: ParseResult) {
    const next = r.spec ?? r.draft_spec;
    if (next) setSpec({ ...next, seed: next.seed ?? spec.seed });
  }

  function pick(polarity: "include" | "exclude", o: EntityOption) {
    setSpec((s) => setState(s, o.kind, o.id, polarity));
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <Link href="/dashboard" className="text-sm text-muted hover:text-text">
            ← Playlists
          </Link>
          <h1 className="text-2xl font-semibold">{playlistName || "Loading…"}</h1>
        </div>
        {facets && (
          <p className="text-sm text-muted">
            {facets.artists.length} artists · {facets.albums.length} albums
          </p>
        )}
      </div>

      {error && (
        <p role="alert" className="rounded-md bg-danger-soft p-3 text-danger">
          {error}
        </p>
      )}
      {needsImport && (
        <div className="space-y-2 rounded-md border border-border bg-surface p-4 text-sm">
          <p>This playlist has not been imported yet, or its 24-hour copy expired.</p>
          <button
            type="button"
            onClick={importNow}
            disabled={importing}
            className="rounded-md bg-accent px-4 py-2 font-medium text-white disabled:opacity-50 dark:text-black"
          >
            {importing ? "Importing…" : "Import from Spotify"}
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[360px_1fr]">
        <aside className="min-w-0 space-y-6">
          <QueryBox onParse={(t) => api.parse(playlistId, t)} onApply={applyParsed} onPick={pick} />
          {facets ? (
            <>
              <EntityFilter
                label="Artists"
                rows={artistRows}
                stateOf={(id) => stateOf(spec, "artist", id)}
                onChange={(id, st) => setSpec((s) => setState(s, "artist", id, st))}
              />
              <EntityFilter
                label="Albums"
                rows={albumRows}
                stateOf={(id) => stateOf(spec, "album", id)}
                onChange={(id, st) => setSpec((s) => setState(s, "album", id, st))}
              />
            </>
          ) : (
            <p className="text-sm text-muted">Loading artists and albums…</p>
          )}
          <ShuffleControls spec={spec} onChange={setSpec} />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => run(spec)}
              disabled={loading}
              className="flex-1 rounded-md bg-accent px-4 py-2.5 font-medium text-white disabled:opacity-50 dark:text-black"
            >
              {loading ? "Building…" : "Generate preview"}
            </button>
            {(hasFilters(spec) || spec !== DEFAULT_SPEC) && (
              <button
                type="button"
                onClick={() => {
                  setSpec(DEFAULT_SPEC);
                  setPreview(null);
                }}
                className="rounded-md border border-border px-3 py-2 text-sm"
              >
                Reset
              </button>
            )}
          </div>
        </aside>

        <div className="min-w-0 space-y-6">
          {preview ? (
            <>
              <QueuePreview preview={preview} />
              {preview.queue.length > 0 && (
                <ExportPanel key={previewVersion} preview={preview} playlistName={playlistName || "PlaylistIQ"} live={live} />
              )}
            </>
          ) : (
            <div className="rounded-lg border border-dashed border-border p-10 text-center text-muted">
              Choose artists or albums, or type a request, then generate a preview. With no rules, every song in the
              playlist is used.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
