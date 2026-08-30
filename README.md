# tg2spotify

**Do you also have this problem — hundreds of songs sitting in a Telegram
channel that never made it into your Spotify?**

This tool reads a Telegram channel export, fixes the broken artist/title tags
(Telegram exports are notoriously messy: empty fields, swapped artist/title,
channel spam baked into the name), matches each track against Spotify's real
catalog, and adds the matches to a playlist — for hundreds of tracks at once,
without you typing a single song name by hand.

It was built and tested end-to-end on a real, messy archive: 738 tracks, 8.5
years of posts, mixed Persian and international music. 642 of them (87%)
ended up in the playlist automatically. [Read the full story, including
every bug real data exposed →](docs/ARTICLE.en.md) ([فارسی](docs/ARTICLE.fa.md))

## Do you need AI to run this?

**No.** Every step below is a plain Python script — regexes, a similarity
score, HTTP calls to Spotify. Nothing here calls an LLM, and a normal run is
just the commands in "Run it" below, or `./autopilot.sh` for the whole thing
unattended.

An AI (Claude) was used to *build* this and debug it against one real messy
channel — see the article above for that whole story. The one place AI (or
manual regex-writing) might still help *you* specifically: `clean.py`'s
cleaning rules were tuned to one channel's junk patterns. If your channel's
mess looks different, you may need to extend a few regexes in one file —
that's a one-time edit, not a requirement to run the tool.

## What you need

- Python 3 — no extra packages, pure standard library
- A Telegram channel export (from Telegram Desktop, JSON format)
- A free Spotify Developer account (2 minutes, no credit card)

## Quick start

### 1. Export your Telegram channel

Telegram Desktop → the channel → ⋮ menu → **Export chat history** → format
**Machine-readable JSON**.

**Skip downloading the audio if you can.** There's a media size-limit slider
in the export dialog — drag it to the minimum. You still get every song's
artist, title, caption, filename, and (for almost all tracks) duration; you
just skip downloading gigabytes of audio you don't strictly need. Measured on
this project's own 738-track run: only 1.5% of tracks needed the actual file
for anything.

### 2. Create a free Spotify app

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
   and create an app (any name/description).
2. Set its **Redirect URI** to exactly: `http://127.0.0.1:8888/callback`
3. Tick **Web API**, save, and copy the **Client ID**.

No client secret is ever needed — this uses PKCE, where the client ID alone
is enough.

### 3. Point the tool at both

```bash
echo YOUR_SPOTIFY_CLIENT_ID > .client_id
echo '/path/to/ChatExport_YYYY-MM-DD' > .export_path
```

Both files are gitignored — never commit a client ID. (It's not a secret in
the security sense, but anyone running with it spends *your* Spotify search
quota and inherits your rate-limit bans.)

### 4. Run it

```bash
python3 tests/run_tests.py        # confirms your setup works: 111 offline tests
python3 run_ingest.py             # reads the export, fixes names, generates search candidates
python3 run_match.py 20           # tries the first 20 tracks against Spotify, to sanity-check
python3 run_match.py              # the rest (safe to re-run any time; picks up where it left off)
```

The first `run_match.py` opens Spotify in your browser once, for a single
consent click. After that it's silent.

### 5. Push to a playlist

```bash
python3 run_push.py "My playlist name" "<playlist-id-or-url>" --include-review
```

Pass a playlist you've already created (paste its share link or ID) — the
tool adds matches to it and never adds the same track twice, even if you run
this again. `--include-review` also publishes the tracks the matcher wasn't
fully sure about (see "The ones it's not sure about" below); drop the flag to
publish only its confident matches.

### 6. Check the results

```bash
python3 status.py       # one-screen summary: matched / unsure / not found
python3 run_audit.py    # one CSV of everything worth a manual listen
```

## Got more than a couple hundred tracks?

Spotify's search quota runs out after a few hundred requests and comes back
hours later. Instead of running steps 4–5 by hand every time the quota
clears, let it manage itself:

```bash
nohup ./autopilot.sh "My playlist name" "<playlist-id>" --include-review &
```

It matches what it can, pushes it, and — if the quota runs out — sleeps
exactly as long as Spotify asked, then picks back up automatically. Safe to
interrupt (Ctrl-C) and re-run any time; keeps going until every track is
resolved. `nohup` means it survives you closing the terminal.

## The ones it can't find

Some tracks genuinely aren't on Spotify — remixes, live bootlegs, unofficial
uploads. These land in `reports/not_found.csv`, one row per track with a
ready `open.spotify.com/search/...` link — click, check, add by hand if it
turns out to exist after all.

## The ones it's not sure about

`run_audit.py` writes `reports/suspects.csv`: every track that was never
found, every track published despite the matcher being unsure, and every
automatic match whose own score was borderline. Worth a quick manual listen
before you trust the playlist completely — matching by text and duration is
good, not infallible (a note-perfect cover by a different artist can fool
it; see the article for a real example).

## No dependencies, on purpose

Pure Python standard library, no `pip install` needed. `difflib` stands in
for `rapidfuzz`, `urllib` for `requests`, and `src/tg2spotify/id3.py` is a
small hand-written ID3 reader standing in for `mutagen`.

## More

- **[docs/ARTICLE.en.md](docs/ARTICLE.en.md)** / **[docs/ARTICLE.fa.md](docs/ARTICLE.fa.md)** — the full write-up: every technique, every bug, every alternative considered.
- **[docs/OPERATIONS.md](docs/OPERATIONS.md)** — Spotify API quirks, resuming, and what one real 738-track run measured.
- **[docs/superpowers/specs/](docs/superpowers/specs/)** — the original design document.
