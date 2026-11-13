# Architecture

```
Browser ──► Next.js (frontend/, port 3000)
              │  /api/* and /health are proxied server-side
              ▼
           FastAPI (backend/, port 8000)
              │
              ├─ api/            HTTP routes and response models
              ├─ engine/         pure functions: models, filters, shuffle, metrics, query_parser
              ├─ services/       PlaylistSource seam: demo source today, Spotify source next
              ├─ spotify/        async client (pagination, retries, rate limits) and normalizer
              └─ auth/           PKCE helpers
```

The browser only talks to the Next.js server. API calls are proxied, so live-mode session cookies
will be first-party and Spotify tokens never reach the browser.

Everything that decides *which* songs and *in what order* lives in `backend/app/engine/` as pure
functions over `PlaylistEntry` objects. They do no I/O, so they are fast to test and benchmark and
behave the same for demo data and live Spotify data.

## Data model

`PlaylistEntry` is one **occurrence** in a playlist, keyed by `entry_id` (`playlist-id:position`).
The same song added twice is two entries with the same `track_id`, and both survive filtering and
shuffling. Artists and albums without Spotify IDs (local files) get a name-based key such as
`local-artist:basement static`.

## Filtering (`engine/filters.py`)

1. Inside an include list, values are OR-ed ("Kiro or Lumen Hart").
2. Categories are AND-ed (artist include AND album include).
3. Exclusions always win.
4. An empty include list means no restriction.
5. The same ID in both an include and an exclude list is rejected with a validation error.

An entry matches an artist rule if **any credited artist** matches. `primary_artist_only` limits
matching to the first-credited artist. Filtering preserves playlist order.

## Ordering (`engine/shuffle.py`)

**True random** is Durstenfeld's Fisher-Yates shuffle over entries. A chi-square test over all 24
permutations of four items (48,000 draws) checks uniformity.

**Balanced** places one entry per slot so that no entry shares a credited artist with any of the
previous `k` entries (`minimum_artist_gap = k`).

- Entries are grouped by their exact set of credited artists. Entries in a group are
  interchangeable for spacing, so the search picks a group, then a uniformly random entry from it.
- Groups that contain an artist placed in the last `k` slots are *blocked* and have zero weight in
  a Fenwick tree. Every weighted draw is therefore valid, at O(log groups) per draw.
- Weight is `entries_in_group × (remaining entries of its busiest artist) ^ 0.5`. Favouring
  artists with many entries left avoids dead ends; the square root keeps them from being pulled to
  the front. With exponent 1.0 the dominant artist's mean position was about 0.47 instead of 0.50
  (see `docs/benchmarks.md`).
- **Lookahead.** An artist with `c` entries left that can next play after `w` slots needs
  `w + (c - 1)(k + 1)` more slots. If that equals the slots remaining, the artist must play now;
  if it exceeds them, the attempt is a dead end.
- **Up-front proof of infeasibility.** If any artist has `(c - 1)(k + 1) + 1 > n`, no valid order
  exists, and strict mode says so immediately, naming the artist and the largest gap that would
  work.
- **Strict mode** tries 10 randomized attempts, then 3 deterministic "most remaining first"
  attempts. For 60 entries or fewer it then runs an exhaustive search (200,000-node budget). If
  the search finishes without an answer, the result is a proven `infeasible` (this catches cases
  such as collaborations that make every pair of songs collide). If the budget runs out, the
  result is `not_found`, which is not presented as proof.
- **Relaxed mode** never fails. When nothing is eligible it places the entry whose conflict lies
  furthest back, and records each violation (position, conflicting position, shared artists). An
  independent checker (`find_violations`) recomputes them in the tests.
- If every selected entry shares one artist, balanced mode explains that variety cannot be
  increased: strict mode reports infeasible, relaxed mode falls back to a uniform shuffle.

**Recently added** sorts by `added_at`, newest first, and shuffles only within bands of
`recently_added_band_days` (30 by default; 0 means strict newest-first). It is labelled as not a
uniform shuffle.

Every mode takes a seed. Without one, the server draws a 53-bit seed, returns it, and the same seed
with the same inputs reproduces the order. Seeds stay below 2^53 so they survive JavaScript.

## Query parser (`engine/query_parser.py`)

Rule-based and offline. Steps: normalize text; flag and blank out unsupported requests (play
counts, popularity, moods, years, playback control); extract ordering instructions (gap, mode,
strict, seed, primary-artist-only); find the longest artist and album names that exist in this
playlist; assign include or exclude from trigger words ("except", "no", "without", "only"…);
resolve artist-or-album collisions from cue words ("by", "from", "album") or a neighbouring item
in a list; then build a validated `QuerySpec`.

It never guesses: same-named artists, album titles shared by different artists, and bare surnames
come back as **ambiguities** with options, and no runnable spec is returned until the user picks.
Names not in the playlist come back as **unrecognized**. Editions of one album ("Overlook" and
"Overlook (Deluxe)") are applied together, with a note.

## Live mode: sign-in, storage and export

- **Sign-in** uses Authorization Code with PKCE. `/api/auth/spotify/start` stores the state and
  code verifier in a signed, HttpOnly, 10-minute cookie; the callback checks the state in constant
  time before exchanging the code.
- **Sessions** are random tokens in an HttpOnly, SameSite=Lax cookie; the database stores only
  their SHA-256 hash. Spotify tokens are encrypted at rest with Fernet, using a key derived from
  `PLAYLISTIQ_SESSION_SECRET`.
- **CSRF**: every write under `/api` must carry an `X-PlaylistIQ: 1` header, which a cross-site
  page cannot add without passing CORS.
- **Storage** (SQLAlchemy 2 + Alembic; SQLite by default, Postgres supported): `users`,
  `spotify_connections`, `sessions`, `playlist_caches`, `export_jobs`, `export_job_batches`. An
  imported playlist is stored as one JSON document per user with a 24-hour expiry instead of
  permanent track, artist and album tables, to keep retained Spotify data to what the preview
  needs. Deleting a user cascades to all of it.
- **Ownership**: Spotify playlists are only ever read from the signed-in user's own cache. Another
  user's playlist or export job is indistinguishable from one that does not exist.
- **Export** creates a private playlist, saves its ID immediately, adds items in batches of 100,
  and records each batch. A retry reuses the saved playlist, first reads how many items it already
  holds (adding is not idempotent on Spotify's side), and stops rather than guessing if the
  playlist was edited in between. The finished playlist is read back and compared item by item.

## Spotify client

`spotify/client.py` follows `next` links, waits for `Retry-After` on 429 (up to a cap), surfaces
`QUOTA_EXCEEDED` immediately, backs off with jitter on 5xx and network errors, refreshes an
expired token once per request, and maps 403/404 to typed errors. See
`docs/spotify-compatibility.md` for endpoint status and the remaining work.
