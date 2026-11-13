# Spotify compatibility

**Last checked: 13 November 2026**, by reading Spotify's public developer documentation.
Nothing below has been tested against the live API yet, because the project does not have a
registered Spotify app. Every live-API claim here is "documented", not "verified by a call".
Re-check before relying on it: Spotify changed Development Mode substantially in 2026.

Pages read:

- [February 2026 Web API Dev Mode changes: migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide)
- [Web API changelog, February 2026](https://developer.spotify.com/documentation/web-api/references/changes/february-2026)
- [Quota modes](https://developer.spotify.com/documentation/web-api/concepts/quota-modes)
- [Redirect URIs](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri)
- [Get playlist items](https://developer.spotify.com/documentation/web-api/reference/get-playlists-items)
- [Add items to playlist](https://developer.spotify.com/documentation/web-api/reference/add-items-to-playlist)
- [Developer Policy](https://developer.spotify.com/policy) (effective 15 May 2025)
- [Developer Terms](https://developer.spotify.com/terms) (version 10, effective 15 May 2025; read in part)

Not yet read: the March 2026 and July 2026 changelogs, the remove/reorder item references, the
create-playlist reference, and the Data Protection Appendix of the Developer Terms.

## Endpoints PlaylistIQ uses

| Purpose | Endpoint | Status in docs | Scope | Notes |
|---|---|---|---|---|
| Sign in | Authorization Code with PKCE (`accounts.spotify.com/authorize`, `/api/token`) | Available | — | No client secret needed. `state` is checked on the callback. |
| Current user | `GET /v1/me` | Available | — | `email`, `country`, `product`, `followers` and `explicit_content` were removed from the response in Feb 2026. |
| List the user's playlists | `GET /v1/me/playlists` | Available | `playlist-read-private`, `playlist-read-collaborative` | `GET /users/{id}/playlists` was removed. |
| Read a playlist's songs | `GET /v1/playlists/{id}/items` | Available (renamed from `/tracks`) | `playlist-read-private` | **Only for playlists the user owns or collaborates on.** Others return 403. `limit` max is 50. |
| Playlist metadata | `GET /v1/playlists/{id}` | Available | — | For playlists the user does not own, `items` is omitted. |
| Create the export playlist | `POST /v1/me/playlists` | Available (replaces `POST /users/{id}/playlists`) | `playlist-modify-private` | Export creates a private playlist. |
| Add songs to it | `POST /v1/playlists/{id}/items` | Available (renamed from `/tracks`) | `playlist-modify-private` | At most 100 URIs per request. Sent in the JSON body. |

Field changes handled by `backend/app/spotify/normalize.py`:

- Playlist entries now carry the song in `item`. The old `track` key is still returned but is
  marked deprecated; the normalizer reads `item` first and falls back to `track`.
- Track `popularity`, `available_markets` and `linked_from` were removed. PlaylistIQ never used
  popularity, and "deep cuts" mode stays unimplemented because no honest popularity source remains.
- `item` can be null for removed or unavailable songs; those are skipped and counted.
- Local files have no Spotify IDs; they are matched by name and cannot be exported.
- Podcast episodes are skipped and counted.

Endpoints PlaylistIQ deliberately does not use: playback and queue control (the app never claims
to control what Spotify plays), batch `GET /tracks` and `GET /artists` (removed in Dev Mode),
search, and recommendations.

## Development Mode limits that affect this project

- **The app owner needs Spotify Premium.** Development Mode apps stop working if the owner's
  Premium subscription lapses.
- **Up to 5 users**, each added by hand on the app's *User Management* tab. Anyone else gets 403.
- **Only owned or collaborative playlists can be read.** A playlist someone else made (including
  Spotify's own editorial playlists) cannot be imported, even if the user follows it. The UI must
  say this plainly.
- **Extended Quota** (more users) is only open to organizations, not individuals, so a public
  portfolio deployment stays at 5 allowlisted users. The public site runs in demo mode for
  everyone else.
- **Quota**: exceeding the Dev Mode quota returns 429 with `reason: QUOTA_EXCEEDED`. The client
  surfaces this instead of retrying, because waiting does not help.

## Redirect URIs

- HTTPS is required, except for loopback addresses.
- `localhost` is **not** allowed. Use `http://127.0.0.1:PORT/...` (or `http://[::1]:PORT/...`).
- Local default: `http://127.0.0.1:8000/api/auth/spotify/callback`.

## Policy constraints and how the design follows them

| Rule (Developer Policy / Terms) | What PlaylistIQ does |
|---|---|
| Do not use Spotify Content to train, or otherwise ingest it into, an ML or AI model (Policy III.14, Terms IV.2.1). | The query parser is rule-based and runs locally. No playlist data is sent to any AI model. A model-based parser could only ever see the user's own typed text, never playlist metadata, and is not built. |
| Do not create new or derived listenership metrics or benchmark the Service (Policy III.13). | The app reorders a user's own selection for their own listening. The published benchmarks use synthetic data only and measure this app's algorithms, not Spotify. |
| Store Spotify Content only as strictly necessary; do not store it indefinitely (Terms IV.3.1, IV.3.2). | Live mode will cache a playlist only to build previews and exports, with an expiry, and delete it on disconnect. |
| Delete a user's Spotify personal data when they disconnect (Policy I.2, Terms V.8). | Disconnect will delete tokens and cached playlists. (Live mode not built yet.) |
| Do not sell or pass Spotify data to ad networks or data brokers (Terms IV.2.5, V.5). | No analytics, ads or third-party data sharing. |
| Do not commit Spotify-derived data to the public repo. | All sample data is generated by `scripts/generate_sample_data.py` and is fictional. |

## Status

| Piece | State |
|---|---|
| Demo mode (synthetic data, no network) | Working, tested |
| API client: pagination, 429 `Retry-After`, quota handling, 5xx backoff, token refresh, 403 | Built and tested against mocked responses (`tests/test_spotify.py`), including a 2,000-item, 40-page fixture |
| Item normalizer (`item`/`track`, local files, nulls, episodes, duplicates) | Built and tested |
| PKCE helpers (verifier, S256 challenge, state check) | Built and tested against the RFC 7636 example |
| Sign-in routes, sessions, token storage, Postgres cache | **Not built yet** (next milestone) |
| Export with idempotency and progress | **Not built yet** |
| Live end-to-end check (OAuth, read, create, add) | **Awaiting a Spotify app and credentials** |

## Setting up a Spotify app (when you are ready for live mode)

1. Make sure the Spotify account that will own the app has **Premium**.
2. Go to <https://developer.spotify.com/dashboard>, sign in, accept the Developer Terms, and click
   **Create app**.
3. Name and description: anything, for example "PlaylistIQ (dev)".
4. Redirect URI: `http://127.0.0.1:8000/api/auth/spotify/callback` (exactly this, with
   `127.0.0.1`, not `localhost`). Add the deployed URL later when there is one.
5. Under "Which API/SDKs are you planning to use?", tick **Web API**.
6. Save, open the app's **Settings**, and copy the **Client ID**. The client secret is not needed
   because sign-in uses PKCE. Do not paste either into code or chat.
7. On **User Management**, add the Spotify accounts (name and email) allowed to use the app, up to 5.
8. Put the Client ID in `backend/.env` as `PLAYLISTIQ_SPOTIFY_CLIENT_ID=...`.
