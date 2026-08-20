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
python3 tests/run_tests.py     # 38 golden cases, all from real channel data
python3 run_ingest.py          # stage 1+2: export -> state.sqlite + reports/cleaned.csv
```

## Status

| Stage | State |
|---|---|
| 1 ingest (5 metadata sources) | done |
| 2 clean + hypotheses | done, 38 tests green |
| 3 match against Spotify | **needs a Spotify client id** |
| 4 review CSV | not started |
| 6 push to playlist | not started |
| 5 fingerprint | deferred — only if misses > 100 |

## What stage 1+2 produced

- 738 tracks ingested, 145 non-music messages excluded, 1 track Telegram
  refused to export.
- ID3 tags recovered from 622 files as an independent metadata vote.
- 2,845 search hypotheses (~3.9 per track).
- Only **10 tracks** left with no recoverable artist.

Review `reports/cleaned.csv` to audit the cleaning before any Spotify call is made.

## To continue

Create a free app at <https://developer.spotify.com/dashboard>, redirect URI
`http://127.0.0.1:8888/callback`, then export:

```bash
export SPOTIFY_CLIENT_ID=...
export SPOTIFY_CLIENT_SECRET=...
```
