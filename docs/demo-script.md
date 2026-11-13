# Demo script (about 75 seconds)

1. **Landing (5 s).** "PlaylistIQ lets you play exactly the part of a big playlist you want, in an
   order you control." Click **Try the demo**.
2. **Playlists (5 s).** Open *Late Night Rotation*, 2,394 synthetic songs.
3. **Typed request (20 s).** Type *"J. Calder, Nia Solstice and Kiro except Porch Light, no same
   artist back to back"* and press **Apply**. Point out the chips: three artists included, both
   editions of *Porch Light* excluded, balanced order with a gap of 1.
4. **Preview (15 s).** **Generate preview.** "297 of 2,394 songs match, all rules met, zero
   neighbours share an artist, built in about 20 ms." Scroll the queue.
5. **Honesty (15 s).** Type *"only Echo, most played first"*. It asks which of two artists called
   Echo you mean, and explains that play counts are not available from Spotify.
6. **Impossible rules (10 s).** Open *Calder Deep Dive* (one artist), tick **Strict**, generate:
   "Impossible with these rules", with the reason, instead of a fake answer.
7. **Close (5 s).** "Your original playlist is never touched. Export creates a new playlist once
   live Spotify access is connected."

# Portfolio description

**PlaylistIQ** is a full-stack app for searching inside a large playlist and generating a
custom-ordered mix from it. A FastAPI backend holds pure, fully tested engines: a filter engine with
documented include/exclude precedence, a Fisher-Yates shuffle, a constraint-aware "balanced"
shuffle that keeps artists apart using weighted sampling over a Fenwick tree with feasibility
lookahead and proves infeasibility instead of silently breaking rules, and an offline natural-language
parser that resolves names only against the playlist and asks when a name is ambiguous. A Next.js
and Tailwind frontend shows the exact resulting order with its rules and quality metrics. The
project ships with a synthetic 2,394-song dataset, 124 automated tests including Playwright
end-to-end tests, measured benchmarks up to 10,000 songs, and a Spotify client built against the
2026 Web API changes.
