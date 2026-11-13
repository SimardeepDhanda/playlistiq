export default function Settings() {
  return (
    <div className="max-w-2xl space-y-8">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <section className="space-y-2">
        <h2 className="font-medium">Spotify connection</h2>
        <p className="text-sm text-muted">
          Not connected. This build runs in demo mode until a Spotify developer app is registered for it. When
          live mode is available you will be able to connect and disconnect here.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Privacy</h2>
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted">
          <li>Your original playlists are never modified. Export always creates a new playlist, after you confirm.</li>
          <li>Spotify tokens are kept on the server and never stored in your browser.</li>
          <li>Playlist data is cached only as long as needed to build previews, and is deleted when you disconnect.</li>
          <li>Playlist data is never sent to an AI model or third party.</li>
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Cached data</h2>
        <p className="text-sm text-muted">Demo mode stores nothing about you, so there is nothing to delete.</p>
      </section>
    </div>
  );
}
