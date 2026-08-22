# tg2spotify

Imports the music archive of the Telegram channel *Music on 🎧* (738 audio
tracks, exported 2018-01-17 → 2026-08-08) into a Spotify playlist, repairing the
channel's broken metadata first.

Design: [docs/superpowers/specs/2026-08-15-telegram-to-spotify-design.md](docs/superpowers/specs/2026-08-15-telegram-to-spotify-design.md)

## No dependencies

Pure Python standard library — this machine has no `pip`/`venv`
(`apt install python3.12-venv` would be needed). `difflib` stands in for
`rapidfuzz`, `urllib` for `requests`, and `src/tg2spotify/id3.py` is a minimal
ID3v2 reader standing in for `mutagen`.

## Run

```bash
python3 tests/run_tests.py       # 52 tests: cleaning + scoring
python3 run_ingest.py            # stage 1+2: export -> state.sqlite + reports/cleaned.csv
python3 run_match.py 20          # stage 3 on 20 tracks first, to sanity-check
python3 run_match.py             # stage 3 on all 738 (resumable)
python3 run_push.py "Music on 🎧" # stage 6: create the playlist and add matches
```

The first `run_match.py` opens Spotify once for a single consent click, then
caches the token in `.spotify_token.json` (gitignored, mode 600).

## Setup

```bash
echo YOUR_SPOTIFY_CLIENT_ID > .client_id            # from developer.spotify.com/dashboard
echo '/path/to/ChatExport_YYYY-MM-DD' > .export_path # Telegram Desktop -> export, JSON
```

Both files are gitignored. The app's Redirect URI must be exactly
`http://127.0.0.1:8888/callback`, with "Web API" ticked. No client secret is
needed. Never commit a client id: whoever runs with it spends *your* search
quota and inherits your rate-limit bans.

## Resuming (read this first)

```bash
python3 status.py
```

Prints the state and the next command. A skill at
`.claude/skills/tg2spotify/SKILL.md` carries the same operational knowledge
for Claude Code sessions.

## Two Spotify limits that are not bugs

**Use `/playlists/{id}/items`, never `/playlists/{id}/tracks`.** The `/tracks`
sub-resource is retired for newly created apps and answers a bare
`403 {"message": "Forbidden"}` — identical in shape to an app-level ban, with
no hint that the path itself is the problem. `POST /playlists/{id}/items`
works with the same token and the same scopes. Two things confirm the scope was
never at fault: `PUT /playlists/{id}` (editing details, which needs
`playlist-modify-*`) returns 200, and the playlist object itself links to
`…/items`. On `/items` the payload field is named `item`, not `track`; reading
it with the old key silently returns an empty list and makes de-duplication
believe a full playlist is empty. Both are pinned in
`tests/test_playlist_items_path.py`.

Genuinely restricted for this app, with no alternative path found:
`GET|POST /playlists/{id}/tracks`, `GET /users/{id}/playlists`,
`POST /users/{id}/playlists` (use `POST /me/playlists`), and batch
`GET /tracks?ids=` (use single `GET /tracks/{id}`). Working: `/me`,
`/me/playlists`, `/playlists/{id}`, `/playlists/{id}/items`, `/search`,
`/albums/{id}`.

**Search quota bans last hours.** One 429 asked for a 54,879 second
(15.2 hour) wait. `api.RateLimited` aborts the run rather than sleeping, and
retrying a banned endpoint can extend the ban - wait, then re-run.

## Current state

| | |
|---|---|
| **in the playlist** | **281** |
| matched | 241 |
| review (published too) | 44 |
| not found | 36 |
| still to match | 417 (waiting on search quota, not on code) |
| exported to `import_list.txt` | 280 |
| target playlist | set locally, see Setup |

Matching costs ~4 searches per track and a quota window allows roughly 600, so
the remaining 417 finish across several windows over several days. Playlist
writes are unaffected by a search ban — push whatever has matched, whenever.

## Status

| Stage | State |
|---|---|
| 1 ingest (5 metadata sources) | done |
| 2 clean + hypotheses | done, 38 tests green |
| 3 match against Spotify | done, 14 scoring tests green |
| 4 review CSV | done (`reports/review.csv`) |
| 6 push to playlist | done, direct via `POST /playlists/{id}/items` |
| 5 fingerprint | deferred — only if misses > 100 |

Configure your own app once (see Setup below). PKCE means no client secret is
used at all.

## What stage 1+2 produced

- 738 tracks ingested, 145 non-music messages excluded, 1 track Telegram
  refused to export.
- ID3 tags recovered from 622 files as an independent metadata vote.
- 2,845 search hypotheses (~3.9 per track).
- Only **10 tracks** left with no recoverable artist.

Review `reports/cleaned.csv` to audit the cleaning before any Spotify call is made.

## Spotify app

Created at <https://developer.spotify.com/dashboard>, redirect URI
`http://127.0.0.1:8888/callback`, Web API, Development mode.

Only needed if you replace the app. No client secret is ever used:

```bash
export SPOTIFY_CLIENT_ID=...
```
