# Run PlaylistIQ on your computer with Spotify

This takes about 10 minutes the first time. You need the Spotify app from
[spotify-compatibility.md](spotify-compatibility.md#setting-up-a-spotify-app-when-you-are-ready-for-live-mode)
(owner on Premium, redirect URI `http://127.0.0.1:8000/api/auth/spotify/callback`, and your own
Spotify account added under **User Management**).

The commands below are for macOS or Linux, typed into the **Terminal** app. Windows notes are at
the end.

## 1. Install the tools (once)

- **Git**: on a Mac, run `git --version`. If it is missing, macOS offers to install it.
- **Node.js 22**: download the "LTS" installer from <https://nodejs.org> and run it.
- **uv** (installs Python for you):

  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

  Close and reopen Terminal afterwards.

## 2. Download the project (once)

```bash
cd ~
git clone https://github.com/SimardeepDhanda/playlistiq.git
cd playlistiq
```

## 3. Add your Spotify Client ID (once)

Replace `YOUR_CLIENT_ID` with the Client ID from the Spotify dashboard:

```bash
echo "PLAYLISTIQ_SPOTIFY_CLIENT_ID=YOUR_CLIENT_ID" > backend/.env
```

This creates the settings file `backend/.env`. It is ignored by git, so it never reaches GitHub.

## 4. Start the API (Terminal window 1)

```bash
cd ~/playlistiq/backend
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Leave this window open. It is ready when it prints `Application startup complete`.

## 5. Start the website (Terminal window 2)

Open a second Terminal window (Cmd+N):

```bash
cd ~/playlistiq/frontend
npm ci
npm run dev
```

## 6. Use it

1. Open **<http://127.0.0.1:3000>**. Use `127.0.0.1`, not `localhost`: Spotify only accepts that
   address.
2. Click **Connect Spotify**, sign in, and approve.
3. On **Playlists**, click **Import** next to one of your playlists, then **Open**.
4. Pick artists or type a request, then **Generate preview**.
5. Click **Export to Spotify**, confirm, and open the new playlist. Turn Spotify's shuffle off so
   it plays in this order.

To stop, press Ctrl+C in both Terminal windows. Next time, only steps 4 to 6 are needed (skip
`uv sync` and `npm ci` unless you pulled new code with `git pull`).

## If something goes wrong

| What you see | What to do |
|---|---|
| "Spotify refused this account" | Add your Spotify account's email under **User Management** in the Spotify dashboard. |
| "INVALID_CLIENT: Invalid redirect URI" on Spotify's page | The redirect URI in the Spotify dashboard must be exactly `http://127.0.0.1:8000/api/auth/spotify/callback`. |
| "The sign-in link expired or did not match" | Open <http://127.0.0.1:3000> (not `localhost`) and try again. |
| "Not yours, so Spotify won't share its songs" | Spotify only allows reading playlists you own or collaborate on. Copy the songs into a playlist of your own in Spotify, then import that one. |
| Connect Spotify says "not set up on this server" | `backend/.env` is missing or misspelled. Repeat step 3, then restart step 4. |
| `command not found: uv` | Close and reopen Terminal after installing uv. |

## Windows

Install Git from <https://git-scm.com>, Node.js 22 from <https://nodejs.org>, and uv with
`powershell -c "irm https://astral.sh/uv/install.ps1 | iex"` in PowerShell. Then run the same
commands in PowerShell, replacing step 3 with:

```powershell
Set-Content backend\.env "PLAYLISTIQ_SPOTIFY_CLIENT_ID=YOUR_CLIENT_ID"
```
