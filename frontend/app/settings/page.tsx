"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api } from "@/lib/api";
import { connectSpotify } from "@/lib/connect";
import { useAuth } from "@/lib/useAuth";

const AUTH_ERRORS: Record<string, string> = {
  denied: "You cancelled the Spotify sign-in.",
  state_mismatch: "The sign-in link expired or did not match. Please try again.",
  token_exchange: "Spotify did not accept the sign-in. Please try again.",
  not_allowlisted:
    "Spotify refused this account. In Development Mode, every user must be added on the app's User Management page in the Spotify dashboard.",
  profile: "Could not read your Spotify profile. Please try again.",
  spotify_error: "Spotify reported an error during sign-in.",
};

export default function SettingsPage() {
  return (
    <Suspense>
      <Settings />
    </Suspense>
  );
}

function Settings() {
  const auth = useAuth();
  const router = useRouter();
  const code = useSearchParams().get("auth_error");
  const authError = code ? (AUTH_ERRORS[code] ?? "Sign-in failed.") : null;
  const [confirm, setConfirm] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  async function disconnect() {
    await api.deleteMe();
    setDone("Disconnected. Your tokens, imported playlists and export history have been deleted.");
    setConfirm(false);
    setTimeout(() => router.push("/"), 1500);
  }

  return (
    <div className="max-w-2xl space-y-8">
      <h1 className="text-2xl font-semibold">Settings</h1>
      {authError && (
        <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
          {authError}
        </p>
      )}
      {done && (
        <p role="status" className="rounded-md bg-accent-soft p-3 text-sm text-accent">
          {done}
        </p>
      )}

      <section className="space-y-2">
        <h2 className="font-medium">Spotify connection</h2>
        {!auth && <p className="text-sm text-muted">Checking…</p>}
        {auth && !auth.connected && (
          <p className="text-sm text-muted">
            Not connected.{" "}
            {auth.spotify_configured ? (
              <button type="button" onClick={connectSpotify} className="text-accent underline">
                Connect Spotify
              </button>
            ) : (
              "This server has no Spotify app configured, so only demo mode is available."
            )}
          </p>
        )}
        {auth?.connected && (
          <div className="space-y-3 text-sm">
            <p>Connected as {auth.display_name ?? "your Spotify account"}.</p>
            {!confirm ? (
              <button
                type="button"
                onClick={() => setConfirm(true)}
                className="rounded-md border border-danger px-4 py-2 text-danger"
              >
                Disconnect and delete my data
              </button>
            ) : (
              <div role="alertdialog" aria-labelledby="del-title" className="space-y-2 rounded-md bg-danger-soft p-3">
                <p id="del-title" className="text-danger">
                  This deletes your stored Spotify tokens, imported playlists and export history from PlaylistIQ.
                  Playlists already created in Spotify stay there.
                </p>
                <div className="flex gap-2">
                  <button type="button" onClick={disconnect} className="rounded-md bg-danger px-4 py-2 text-white">
                    Delete
                  </button>
                  <button type="button" onClick={() => setConfirm(false)} className="rounded-md border border-border px-4 py-2">
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Privacy</h2>
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted">
          <li>Your original playlists are never modified. Export always creates a new private playlist, after you confirm.</li>
          <li>Spotify tokens are encrypted on the server and never stored in your browser.</li>
          <li>Imported playlists are kept for 24 hours to build previews, then deleted. Disconnecting deletes everything.</li>
          <li>Playlist data is never sent to an AI model or third party.</li>
        </ul>
      </section>
    </div>
  );
}
