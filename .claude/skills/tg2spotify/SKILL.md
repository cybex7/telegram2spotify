---
name: tg2spotify
description: Use when resuming the Telegram-channel-to-Spotify music import in this repo - matching remaining tracks, refreshing the import list, or diagnosing a 403/429 from Spotify, or pushing to the playlist. Run status.py first; do not re-explore the repo.
---

# tg2spotify

Imports 738 audio tracks from the Telegram channel *Music on 🎧* into Spotify,
repairing the channel's mangled metadata first.

## Start here, always

```bash
python3 status.py     # from the repo root
```

That prints counts, the stored playlist id, report line counts, and the exact
next command. **Read it instead of exploring** — no `ls`, no schema dumping, no
re-reading the spec. The design rationale lives in
`docs/superpowers/specs/2026-08-15-telegram-to-spotify-design.md`; open it only
if changing the approach, not to resume.

## The three commands

```bash
python3 tests/run_tests.py   # 100 tests, all offline. Run after ANY code change.
python3 run_match.py         # match remaining tracks against Spotify (resumable)
python3 run_push.py "Music On" "<playlist-id>" --include-review   # push (idempotent)
python3 run_export.py        # refresh reports/import_list.txt + .csv
python3 run_audit.py         # not-found + published-review + weak-auto-match, one CSV
./autopilot.sh "Music On" "<playlist-id>" --include-review   # match+push+export on a loop, no AI needed
```

Everything is resumable through `state.sqlite`; re-running never repeats
finished work. Stdlib only — this machine has **no pip and no venv**
(`ensurepip` is missing). `difflib` stands in for rapidfuzz, `urllib` for
requests, `src/tg2spotify/id3.py` for mutagen. Do not add a dependency.

## Two Spotify limits that are NOT bugs

**Playlist writing works — through `/items`, not `/tracks`.** `POST
/playlists/{id}/items` succeeds. The retired `/playlists/{id}/tracks` answers a
bare `403 {"message": "Forbidden"}` that is indistinguishable from an app-level
ban, and reading it as one wasted a full day of work. Two cheap checks prove the
scope is fine: `PUT /playlists/{id}` (needs `playlist-modify-*`) returns 200,
and the playlist object links to `…/items`. **On `/items` the payload field is
`item`, not `track`** — the old key returns an empty list and makes dedup think
a full playlist is empty. Pinned in `tests/test_playlist_items_path.py`.

Actually restricted, no alternative path found: `/playlists/{id}/tracks`,
`GET|POST /users/{id}/playlists` (use `POST /me/playlists`), batch
`GET /tracks?ids=` (use single `GET /tracks/{id}`). Working: `/me`,
`/me/playlists`, `/playlists/{id}`, `/playlists/{id}/items`, `/search`,
`/albums/{id}`. `reports/import_list.txt` is now a fallback, not the delivery.

**Search quota bans last hours, and quota is the real budget.** Observed
`Retry-After` values: 54879s (15.2h) and 85838s (23.8h). `api.RateLimited`
aborts the run immediately; progress is committed and `run_match.py` still
writes the reports before exiting 2. Never loop or retry against it — repeat
calls can extend the ban.

Budget the work in searches, not in tracks. Measured: ~4 searches per track, and
a window seems to allow roughly 600 before the ban, so **one window matches
about 150 tracks**. The remaining work therefore spans days. Two consequences:

- `run_match.py` skips `review`/`miss` tracks by default. Re-trying them cost
  353 searches to convert 1 track — over half a window for nothing. Use
  `--retry-hard` only after changing the cleaning or scoring rules.
- **The ban is on `/search` alone.** `POST /playlists/{id}/items` and
  `GET /tracks/{id}` keep working through it, so always push and export after an
  aborted match run rather than waiting.

## Facts worth not re-deriving

- Export path comes from `.export_path`; this archive had 904 messages,
  738 audio, covering 2018-01-17 → 2026-08-08.
- Excluded: 331 `*_thumb.jpg`, 126 voice messages, 17 videos, 1 oversized track.
- Target playlist id is stored in the `meta` table (created by hand; `POST
  /me/playlists` should also work). Client id comes from `.client_id` (never
  committed) and `.spotify_token.json` holds the refresh token — both gitignored.
- User's decisions: publish `review` matches too; accept a few wrong-version
  tracks; a manual pile under 100 is fine; fingerprinting (stage 5) stays
  unbuilt unless misses exceed 100.
- **The media download is close to skippable.** Only 4/660 successful matches
  (0.6%) were decided by the ID3 tag vote, and only 11/738 tracks (1.5%)
  lacked a `duration_seconds` in the JSON and needed the file. `ingest.py`
  checks each file's presence individually, so a JSON-only export (media
  size-limit slider dragged to minimum in Telegram Desktop's export dialog)
  works with no code change.

## Rules that cost real time when ignored

- **Never `pkill -f run_match.py`.** The pattern matches your own shell and
  kills the tool call (exit 144, happened twice). Use
  `ps -eo pid=,comm=,args= | awk '$2=="python3" && /run_matc/ {print $1}'`
  then `kill` those pids.
- **Watch progress, not liveness.** A stalled run looks identical to a healthy
  one; an 8-hour sleep on a Retry-After went unnoticed because the watcher only
  checked whether the process had exited. Poll the row count.
- **Redirect nohup output through `python3 -u`,** or block buffering hides
  every message until exit.
- **Never push while a match run is going.** A re-match moves a track to a
  better URI, and the URI already pushed becomes an orphan — a wrong song in the
  playlist with no row pointing at it. Happened once; `run_push.py` now counts
  orphans in its output and `--prune` removes them. Do not prune blindly: it
  also deletes tracks the user added to the playlist by hand.
- **Fix defects test-first.** Every real bug here was found by running against
  real data, then pinned with a golden case from the actual channel strings:
  Spotify's dash-suffix qualifiers (`- Remastered 2009`), `&`-joined artists,
  `<unknown>` placeholders, channel branding surviving handle removal, bare
  `with` clauses being stripped from titles.
- **Do not diagnose by guessing.** Read the API error body (now surfaced by
  `api._request`) *and* compare related endpoints before concluding anything.
  "403 Forbidden on a write" was called an app-level ban when it was a retired
  URL path; the refutation was one 200 from `PUT /playlists/{id}`. When an error
  message is generic, the theory is unproven — go find the call that
  distinguishes the theories.

## Layout

| Path | Role |
|---|---|
| `src/tg2spotify/clean.py` | metadata repair + hypothesis generation (pure) |
| `src/tg2spotify/score.py` | title/artist/duration scoring, auto vs review vs reject |
| `src/tg2spotify/match.py` | stage 3 driver, dead-network guard |
| `src/tg2spotify/export.py` | canonical names → import list |
| `src/tg2spotify/{auth,api}.py` | PKCE (client id only, no secret), paced client |
| `src/tg2spotify/{ingest,id3,db,push}.py` | stage 1, ID3 reader, schema, playlist push |
| `reports/import_list.txt` | **the deliverable** |
| `reports/not_found.csv` | manual pile, with ready search URLs |
