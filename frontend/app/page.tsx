import Link from "next/link";

const examples = [
  "Only Marlo Vance",
  "J. Calder from The Long Season",
  "Marlo Vance and J. Calder except Overlook, no same artist back to back",
];

export default function Landing() {
  return (
    <div className="space-y-12">
      <section className="max-w-3xl space-y-5 pt-6">
        <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
          Play exactly the part of your playlist you want.
        </h1>
        <p className="text-lg text-muted">
          PlaylistIQ searches inside one big playlist, keeps only the songs that match your rules, and orders
          them the way you ask: truly random, spread out so the same artist never plays twice in a row, or newest
          additions first. You see the exact order before anything is saved, and your original playlist is never
          changed.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link
            href="/dashboard"
            className="rounded-md bg-accent px-5 py-2.5 font-medium text-white dark:text-black"
          >
            Try the demo
          </Link>
          <span
            className="rounded-md border border-border px-5 py-2.5 text-muted"
            title="Live Spotify access is waiting on a registered Spotify developer app."
          >
            Connect Spotify (coming soon)
          </span>
        </div>
      </section>

      <section aria-labelledby="examples" className="space-y-3">
        <h2 id="examples" className="text-sm font-semibold uppercase tracking-wide text-muted">
          Requests it understands
        </h2>
        <ul className="grid gap-3 sm:grid-cols-3">
          {examples.map((e) => (
            <li key={e} className="rounded-lg border border-border bg-surface p-4 text-sm">
              “{e}”
            </li>
          ))}
        </ul>
      </section>

      <section className="grid gap-6 sm:grid-cols-3">
        {[
          ["Filter, then order", "Include or exclude artists and albums. Collaborations count for every credited artist."],
          ["Honest shuffles", "True random is a Fisher-Yates shuffle. Balanced mode tells you when spacing is impossible instead of quietly breaking it."],
          ["Nothing invented", "Names are matched against the playlist itself. Anything it cannot find or do is shown to you."],
        ].map(([title, body]) => (
          <div key={title} className="space-y-1">
            <h3 className="font-medium">{title}</h3>
            <p className="text-sm text-muted">{body}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
