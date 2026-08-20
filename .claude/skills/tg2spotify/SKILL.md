---
name: tg2spotify
description: Use when resuming the Telegram-channel-to-Spotify music import in this repo - matching remaining tracks, refreshing the import list, or diagnosing a 403/429 from Spotify. Run status.py first; do not re-explore the repo.
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
python3 tests/run_tests.py   # 94 tests, all offline. Run after ANY code change.
python3 run_match.py         # match remaining tracks against Spotify (resumable)
python3 run_export.py        # refresh reports/import_list.txt + .csv
```

Everything is resumable through `state.sqlite`; re-running never repeats
finished work. Stdlib only — this machine has **no pip and no venv**
(`ensurepip` is missing). `difflib` stands in for rapidfuzz, `urllib` for
requests, `src/tg2spotify/id3.py` for mutagen. Do not add a dependency.

## Two Spotify limits that are NOT bugs

**Playlist writing is impossible with this app.** `/playlists/{id}/tracks`
returns 403 for read *and* write, while `/me`, `/me/playlists`,
`/playlists/{id}` and single `/tracks/{id}` all return 200. Batch
`/tracks?ids=` is 403 too. This is Spotify's restriction on newly created
Development-mode apps, not a scope problem. Do not try to "fix" it in code.
Delivery therefore goes through `reports/import_list.txt` and an import
service (Soundiiz / TuneMyMusic), which hold their own write access.

**Search quota bans last hours.** A 429 carried `Retry-After: 54879` (15.2h).
`api.RateLimited` is raised and aborts the run immediately; progress is saved.
Never loop or retry against it — repeat calls can extend the ban. Just wait
and re-run.

## Facts worth not re-deriving

- Export path comes from `.export_path`; this archive had 904 messages,
  738 audio, covering 2018-01-17 → 2026-08-08.
- Excluded: 331 `*_thumb.jpg`, 126 voice messages, 17 videos, 1 oversized track.
- Target playlist is stored in the `meta` table, created by hand because the
  API cannot create one. Client id comes from `.client_id` (never committed).
- User's decisions: publish `review` matches too; accept a few wrong-version
  tracks; a manual pile under 100 is fine; fingerprinting (stage 5) stays
  unbuilt unless misses exceed 100.

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
- **Fix defects test-first.** Every real bug here was found by running against
  real data, then pinned with a golden case from the actual channel strings:
  Spotify's dash-suffix qualifiers (`- Remastered 2009`), `&`-joined artists,
  `<unknown>` placeholders, channel branding surviving handle removal, bare
  `with` clauses being stripped from titles.
- **Do not diagnose by guessing.** Read the API error body (now surfaced by
  `api._request`); a bare "403 Forbidden" cost a whole debug cycle.

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
