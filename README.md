# tg2spotify

Imports the music archive of the Telegram channel *Music on 🎧* (738 audio
tracks, exported 2018-01-17 → 2026-08-08) into a Spotify playlist, repairing the
channel's broken metadata first.

Design: [docs/superpowers/specs/2026-08-15-telegram-to-spotify-design.md](docs/superpowers/specs/2026-08-15-telegram-to-spotify-design.md)

## Do you need an AI to run this?

No. Every stage below is a deterministic Python script -- regexes, a weighted
similarity score, HTTP calls to the Spotify Web API. Nothing in `src/` calls an
LLM, and a normal run is `python3 run_ingest.py && python3 run_match.py &&
python3 run_push.py ...`, or just `./autopilot.sh` for the whole thing
unattended. Clone it, run the scripts, done.

What an AI (Claude) actually did here: wrote this pipeline, and debugged it
against one specific messy real-world Telegram export -- see
[docs/ARTICLE.en.md](docs/ARTICLE.en.md) / [docs/ARTICLE.fa.md](docs/ARTICLE.fa.md)
for the full account, including every bug that real data surfaced. The one
place an AI (or a human, with more regex-writing) might still earn its keep is
`src/tg2spotify/clean.py`: its rules were tuned to *this* channel's junk
patterns (`@handle` spam, specific bracket-junk, Persian folding). A channel
with differently-shaped mess may need those rules extended -- that is a one-time
edit to one file, not a requirement to run the tool at all.

## No dependencies

Pure Python standard library — this machine has no `pip`/`venv`
(`apt install python3.12-venv` would be needed). `difflib` stands in for
`rapidfuzz`, `urllib` for `requests`, and `src/tg2spotify/id3.py` is a minimal
ID3v2 reader standing in for `mutagen`.

## Run

```bash
python3 tests/run_tests.py       # 100 tests: cleaning + scoring + API paths
python3 run_ingest.py            # stage 1+2: export -> state.sqlite + reports/cleaned.csv
python3 run_match.py 20          # stage 3 on 20 tracks first, to sanity-check
python3 run_match.py             # stage 3 on the rest (resumable; aborts clean on a search-quota ban)
python3 run_push.py "Music on 🎧" "<playlist-id>" --include-review  # stage 6, idempotent
python3 run_export.py            # canonical names -> reports/import_list.txt (fallback record)
python3 run_audit.py             # not-found + published-review + weak-auto-match, one CSV
python3 status.py                # one-command state dump; always read this first
```

The first `run_match.py` opens Spotify once for a single consent click, then
caches the token in `.spotify_token.json` (gitignored, mode 600).

For a catalog too large to finish inside one search-quota window, run
`./autopilot.sh "Playlist name" <playlist-id> --include-review` instead of
`run_match.py`/`run_push.py`/`run_export.py` by hand: it loops match -> push ->
export, sleeps exactly as long as Spotify's `Retry-After` says on a 429, and
stops on its own once every track is resolved. `nohup ./autopilot.sh ... &`
survives a closed terminal.

## Setup

```bash
echo YOUR_SPOTIFY_CLIENT_ID > .client_id            # from developer.spotify.com/dashboard
echo '/path/to/ChatExport_YYYY-MM-DD' > .export_path # Telegram Desktop -> export, JSON
```

Both files are gitignored. The app's Redirect URI must be exactly
`http://127.0.0.1:8888/callback`, with "Web API" ticked. No client secret is
needed. Never commit a client id: whoever runs with it spends *your* search
quota and inherits your rate-limit bans.

**You almost certainly do not need to download the audio.** Telegram Desktop's
export dialog has a media size-limit slider (Settings → Advanced → Export
Telegram data); drag it to the minimum and uncheck nothing else -- you still
get the full `result.json` (every `performer`/`title`/`caption`/filename/
`duration_seconds`), just without pulling gigabytes of files. This repo's own
run measured exactly how much that costs: of 660 successful matches, the
audio file's own ID3 tag was the *deciding* source for only **4** (0.6%); of
738 tracks, only **11** (1.5%) lacked a duration in the JSON and needed the
file to supply one. `ingest.py` already checks each file's presence
individually and falls back cleanly when it is absent -- nothing to configure.

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

## Current state — complete

All 738 tracks have been processed and pushed.

| | |
|---|---|
| **in the playlist** | **642** |
| matched automatically | 596 |
| review (published too) | 64 |
| not found (manual pile) | 78 |
| exported to `import_list.txt` | 642 |
| target playlist | https://open.spotify.com/playlist/0TkJ5AgcefGgvG26eGTRze |

642 unique tracks from 660 matched+review rows: the corpus's 12 duplicate
performer+title pairs and 4 duplicate filenames collapse onto shared URIs, as
designed. Verified against the live playlist: 0 missing, 0 extra, 0 orphans.

It took three quota windows across roughly a day and a half — matching runs
~4 searches per track against a ~600-search-per-window ban, so pace future
reruns (e.g. after a cleaning-rule change) accordingly. The 78-track manual
pile is in `reports/not_found.csv`, each row with a ready `open.spotify.com`
search link — under the 100-track threshold the user set as acceptable.

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
