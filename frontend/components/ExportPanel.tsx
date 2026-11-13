export function ExportPanel({ count }: { count: number }) {
  return (
    <div className="space-y-2 rounded-md border border-border bg-surface p-3 text-sm">
      <h3 className="font-medium">Save as a new Spotify playlist</h3>
      <p className="text-muted">
        Export creates a <strong>new</strong> playlist in this exact order ({count.toLocaleString()} songs) and never
        touches the original. Turn Spotify&apos;s own shuffle off when you play it.
      </p>
      <button
        type="button"
        disabled
        aria-describedby="export-why"
        className="rounded-md border border-border px-4 py-2 text-muted"
      >
        Export to Spotify
      </button>
      <p id="export-why" className="text-xs text-muted">
        Not available in demo mode: these songs are synthetic and no Spotify account is connected.
      </p>
    </div>
  );
}
