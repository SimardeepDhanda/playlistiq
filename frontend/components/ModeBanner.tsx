"use client";

import { useAuth } from "@/lib/useAuth";

export function ModeBanner() {
  const auth = useAuth();
  if (auth?.connected) {
    return (
      <div className="border-b border-border bg-accent-soft px-4 py-2 text-center text-sm text-accent" role="note">
        Connected to Spotify as {auth.display_name ?? "you"}. Your original playlists are never changed.
      </div>
    );
  }
  return (
    <div className="border-b border-border bg-warn-soft px-4 py-2 text-center text-sm text-warn" role="note">
      Demo mode: these playlists are synthetic. Every artist, album and song is made up, and no Spotify account is
      connected.
    </div>
  );
}
