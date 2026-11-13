"use client";

import Link from "next/link";
import { connectSpotify } from "@/lib/connect";
import { useAuth } from "@/lib/useAuth";

export function ConnectButton() {
  const auth = useAuth();
  if (!auth) return null;
  if (auth.connected) {
    return (
      <Link href="/dashboard" className="rounded-md border border-border px-5 py-2.5 font-medium">
        Open your Spotify playlists
      </Link>
    );
  }
  if (!auth.spotify_configured) {
    return (
      <span
        className="rounded-md border border-border px-5 py-2.5 text-muted"
        title="This server has no Spotify app configured, so only demo mode is available."
      >
        Connect Spotify (not set up on this server)
      </span>
    );
  }
  // A full page navigation: the API redirects to Spotify's sign-in page.
  return (
    <button
      type="button"
      onClick={connectSpotify}
      className="rounded-md border border-border px-5 py-2.5 font-medium"
    >
      Connect Spotify
    </button>
  );
}
