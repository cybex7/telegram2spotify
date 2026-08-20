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

## Status

| Stage | State |
|---|---|
| 1 ingest (5 metadata sources) | done |
| 2 clean + hypotheses | done, 38 tests green |
| 3 match against Spotify | done, 14 scoring tests green |
| 4 review CSV | done (`reports/review.csv`) |
| 6 push to playlist | done |
| 5 fingerprint | deferred — only if misses > 100 |

Client id `c5f9bf69f8b346c3a9a0df84392eb807` is baked in as the default (it is a
public identifier, not a secret). PKCE means no client secret is used at all.

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
