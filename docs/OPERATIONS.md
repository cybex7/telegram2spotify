# Operations reference

Deeper detail than the main [README](../README.md) — Spotify quirks, resuming
an interrupted run, and what one real run measured. Read the README first;
come here when something needs more context than a quick-start step gives.

## Resuming an interrupted run

```bash
python3 status.py
```

Prints the current state and the exact next command. Everything lives in
`state.sqlite`, so re-running any stage is always safe — matched tracks stay
matched, pushed tracks are never re-added.

A skill at `.claude/skills/tg2spotify/SKILL.md` carries the same operational
knowledge for an AI session resuming this project specifically.

## Two Spotify API quirks that look like bugs but are not

**Use `/playlists/{id}/items`, never `/playlists/{id}/tracks`.** The `/tracks`
sub-resource is retired for newly created apps and answers a bare
`403 {"message": "Forbidden"}` — identical in shape to an app-level ban, with
no hint that the path itself is the problem. `POST /playlists/{id}/items`
works with the same token and the same scopes. Two things confirm the scope
was never at fault: `PUT /playlists/{id}` (editing details, which needs
`playlist-modify-*`) returns 200, and the playlist object itself links to
`…/items`. On `/items` the payload field is named `item`, not `track`;
reading it with the old key silently returns an empty list and makes
de-duplication believe a full playlist is empty. Both are pinned in
`tests/test_playlist_items_path.py`. `src/tg2spotify/api.py` already handles
this — this section exists so nobody "fixes" it back to `/tracks`.

Genuinely restricted for this kind of app, with no alternative path found:
`GET|POST /playlists/{id}/tracks`, `GET /users/{id}/playlists`,
`POST /users/{id}/playlists` (use `POST /me/playlists`), and batch
`GET /tracks?ids=` (use single `GET /tracks/{id}`). Working: `/me`,
`/me/playlists`, `/playlists/{id}`, `/playlists/{id}/items`, `/search`,
`/albums/{id}`.

**Search quota bans last hours, and quota — not code — sets your pace.**
Observed `Retry-After` values: 54879s (15.2h), 85838s (23.8h), 85814s
(23.8h). `api.RateLimited` aborts the run immediately rather than sleeping
through it; retrying a banned endpoint can extend the ban. Every script
still writes its reports and pushes whatever matched before it aborts, so a
ban never wastes the run's progress.

Rough budget: matching costs ~4 searches per track, and a quota window seems
to allow somewhere around 600 searches — so roughly 150 tracks per window.
`./autopilot.sh` (see the README) automates waiting out the ban and
retrying, so a catalog needing multiple windows finishes unattended.

## What one real run measured

Run against 738 tracks from a real, badly-tagged Telegram channel (mixed
Persian and international music, 8.5 years of posts):

| | |
|---|---|
| matched automatically | 596 |
| held for review, published anyway | 64 |
| not found (manual pile) | 78 |
| **ended up in the playlist** | **642** (deduplicated from 660) |

642 unique tracks from 660 matched+review rows: 12 duplicate performer+title
pairs and 4 duplicate filenames in the source channel collapsed onto shared
Spotify URIs, exactly as the de-duplication is designed to do. Verified
against the live playlist afterward: 0 missing, 0 extra, 0 orphans.

It took three search-quota windows across roughly a day and a half — quota,
not code, set the pace. The 78-track manual pile came in under the
100-track threshold this project's original owner considered acceptable to
add by hand; each row in `reports/not_found.csv` carries a ready
`open.spotify.com/search/...` link.

Of the file-dependent metadata: only 11 of 738 tracks (1.5%) lacked a
duration in Telegram's own JSON export and needed the downloaded audio file
to supply one; only 4 of 660 successful matches (0.6%) were decided by the
audio file's own ID3 tags rather than Telegram's own text fields. See the
README's Setup section for what this means for your own export.

## Stage status

| Stage | State |
|---|---|
| 1 ingest (5 metadata sources) | `run_ingest.py` |
| 2 clean + hypotheses | folded into `run_ingest.py`; 38+ tests |
| 3 match against Spotify | `run_match.py`; 14+ scoring tests |
| 4 review / audit CSVs | `run_audit.py` (`reports/suspects.csv`) |
| 5 audio fingerprinting | not built — only worth it if your not-found pile is large; see the design doc |
| 6 push to playlist | `run_push.py`, direct via `POST /playlists/{id}/items` |

## Design rationale

The full reasoning behind the six-stage architecture, the corpus profile
that drove it, and the decisions made along the way:
[docs/superpowers/specs/2026-08-15-telegram-to-spotify-design.md](superpowers/specs/2026-08-15-telegram-to-spotify-design.md)
