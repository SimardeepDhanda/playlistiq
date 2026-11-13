import type { Metadata } from "next";
import Link from "next/link";
import { ModeBanner } from "@/components/ModeBanner";
import "./globals.css";

export const metadata: Metadata = {
  title: "PlaylistIQ",
  description: "Pick exactly which songs from a big playlist to play, and in what order.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen font-sans antialiased">
        <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:p-2">
          Skip to content
        </a>
        <header className="border-b border-border bg-surface">
          <nav className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3" aria-label="Main">
            <Link href="/" className="text-lg font-semibold tracking-tight">
              Playlist<span className="text-accent">IQ</span>
            </Link>
            <Link href="/dashboard" className="text-sm text-muted hover:text-text">
              Playlists
            </Link>
            <Link href="/settings" className="text-sm text-muted hover:text-text">
              Settings
            </Link>
          </nav>
        </header>
        <ModeBanner />
        <main id="main" className="mx-auto max-w-6xl px-4 py-8">
          {children}
        </main>
      </body>
    </html>
  );
}
