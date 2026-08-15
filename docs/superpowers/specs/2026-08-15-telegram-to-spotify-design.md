# Telegram channel → Spotify playlist

**Date:** 2026-08-15
**Status:** Approved design, ready for implementation planning

## Goal

Import the music archive from the Telegram channel *Music on 🎧* into a new public
Spotify playlist, repairing the broken and inconsistent audio metadata before
matching, so tracks match the correct Spotify recording rather than a cover,
karaoke version, or unrelated song.

## Source data

Telegram Desktop export at
`/home/arash/Downloads/Telegram Desktop/ChatExport_2026-08-12/`
(machine-readable JSON, 873 KB, complete and valid; `files/` 6.3 GB).

| Fact | Value |
|---|---|
| Messages total | 904 |
| `audio_file` messages (the corpus) | **738** |
| Files in `files/` (the only subdirectory) | 1065 = 734 media + 331 `*_thumb.jpg` album art |
| Unique real audio files, all present on disk | **733** |
| Formats | mp3 703, m4a 26, flac 5, ogg 4 |
| Exact duplicate `performer`+`title` pairs | 12 |
| Duplicate filenames across audio messages | 4 |

The 738 audio messages resolve to 734 distinct filenames (4 collisions), one of
which is not a file at all but the export-failure placeholder described under
Scope. The remaining **733 audio files are all present on disk — none missing**.

### Metadata completeness

| Field | Missing/empty |
|---|---|
| `performer` | 27 (3.7%) |
| `title` | 18 (2.4%) |
| **both** | **17 (2.3%)** |
| `duration_seconds` | 11 (1.5%) |
| `file` | 0 |

### Contamination requiring cleanup

| Pattern | Tracks | Real example |
|---|---|---|
| Dash separator inside a field | 361 (48.9%) | `Ebi- Hamdam` |
| Bitrate / quality strings | 76 (10.3%) | `[320kbps]`, `[1]` |
| `@handle` channel spam | 64 (8.7%) | `perf=@moozikestan_bot` |
| Persian script | 29 (3.9%) | `مرد تنها - فرهاد` |
| `feat.` / `ft.` variants | 22 (3.0%) | `(Feat. Britt Nicole)` |
| Domains / URLs | 19 (2.6%) | `[IstgahMusic.com]` |
| Bracket junk `[]` `{}` | 14 (1.9%) | `{ON @Sickosadism}` |
| Leading track number — **filename** | 166 | `02 Nakhosh.mp3` |
| Leading track number — title | 7 | `15. The Last Man` |
| Persian `.` used as separator | 4 | `Ghad boland . Korosh yaghmaei` |

### Structural findings driving the design

1. **Separator order is not decidable from the string.** `Ebi- Hamdam` is
   *Artist–Title*; `Kooleh- Kaveh Yaghmaei` is *Title–Artist*. No local rule
   distinguishes them. Both orders must be tried against the real catalog.
2. **`performer` sometimes holds the channel handle while the real artist sits
   in `title`** (`perf=@moozikestan_bot`, `title=Hafez Nazeri - Existence Life`),
   and the two fields are sometimes fully swapped
   (`perf=فرهاد مهراد . آیینه ها`, `title=@Adabvaavayparsi`).
3. **Duration must not be used as a filter.** Of 5 tracks over 12 minutes, 3 are
   genuine songs present on Spotify (Archive *Lights* 18:29, Porcupine Tree
   *Russia On Ice*, Bjorn Riis *Stormwatch*). Duration is a *scoring* signal only.
4. **File extensions are unreliable** — 3 files carry mangled extensions
   (`.mp3 x-amz-content-sh`, `.)`, and 2 with none). Format detection reads file
   headers, never the extension.

## Scope

**In:** the 738 `audio_file` messages.

**Out, with a written report of each exclusion:**

- 331 `*_thumb.jpg` album-art files (not media).
- 126 voice messages (all ≤45s, no `title`/`performer`).
- 17 video files (no titles; decision: skip).
- 1 track Telegram declined to export — `Blues & Bone – Etta James Style
  Acousti…`, `file` field literally reads *"File exceeds maximum size. Change
  data exporting settings to download."* Requires manual re-download if wanted.

## Architecture

Six stages, each a separate module, each independently re-runnable, sharing one
SQLite state file. Resumability is a hard requirement: 738 tracks against a
rate-limited API means partial failure is normal, not exceptional.

```
result.json + files/  →  [1] ingest       → tracks table (5 raw sources each)
                         [2] clean        → ranked (artist,title) hypotheses
                         [3] match        → Spotify search + score → auto/review/miss
                         [4] review       → CSV of ambiguous, human decides
                         [5] fingerprint  → shazamio, misses only
                         [6] push         → batched playlist adds
```

### Stage 1 — ingest

Harvest **five independent metadata sources** per track, stored side by side
rather than collapsed, so later stages can weigh them:

1. Telegram `performer`
2. Telegram `title`
3. Message caption (`text` / `text_entities`)
4. Filename stem
5. Embedded ID3/MP4/FLAC tags read from the file via `mutagen`

Source 5 frequently disagrees with 1–2 and is treated as a distinct vote, not a
fallback. Also records true duration from the file, covering the 11 tracks whose
`duration_seconds` Telegram omitted.

### Stage 2 — clean

Pure functions, string in / structured guesses out. Every transformation logged
with the rule that fired, so any output can be audited back to its input.

**Normalization, in fixed order:**

1. Unicode NFKC; Persian orthography folding (`ي→ی`, `ك→ک`, `ة→ه`), Arabic-Indic
   digits → ASCII, ZWNJ normalized. Without this, two spellings of the same
   Persian artist never compare equal.
2. Strip `@handles`, bare domains (`IstgahMusic.com`, `www.MyYazd-Music11.com`,
   `.ir`), bitrate/quality junk (`320kbps`, `[1]`).
3. Strip leading track numbers `^\d{1,2}[.\-_\s]+` — applied **per field**,
   critical for filenames (166 occurrences).
4. **Bracket contents are judged, not blanket-stripped.** `{ON @Sickosadism}`
   and `[IstgahMusic.com]` are removed; `(feat. Eendo)` and
   `(Rumi Symphony Project: Untold)` are preserved. Blanket paren-stripping
   would destroy real title information.
5. A field reducing to nothing (performer was *only* `@moozikestan_bot`) is
   marked empty so the artist is sourced elsewhere, never searched as a handle.
6. `feat.`/`ft.`/`Feat` → featured artist lifted into its own field; hypotheses
   emitted both with and without it, since Spotify's canonical titles are
   inconsistent about inclusion.

**Hypothesis generation** — the engine does not decide artist vs. title. It
emits an ordered, deduplicated candidate set, capped at ~6 per track:

| # | Hypothesis | Catches |
|---|---|---|
| H1 | cleaned performer + cleaned title | the well-tagged majority |
| H2 | swapped (title as artist) | fully-swapped fields |
| H3 | split title on separator, order A | `Ebi- Hamdam` |
| H4 | split title on separator, order B | `Kooleh- Kaveh Yaghmaei` |
| H5 | same splits on filename stem | the 17 both-null tracks |
| H6 | ID3 tags from the file | when Telegram's attributes are worse |
| H7 | bare title, no artist constraint | last resort |

Roughly 738 × ~4 average ≈ 3,000 searches.

**Persian script is searched as-is.** No transliterator will be written: Spotify
indexes many Farsi artists natively, and the residue is better served by
fingerprinting, which ignores text entirely. A hand-rolled romanizer would be a
large rule pile solving a problem stage 5 already solves properly.

### Stage 3 — match

Spotify search using field-qualified queries (`track:… artist:…`). Each returned
candidate scored on three signals:

- title similarity (`rapidfuzz`, normalized)
- artist similarity (`rapidfuzz`, normalized)
- **duration delta vs. the actual file** — the signal broken tags cannot fake

Outcomes:

- **auto-accept** — strong text match *and* duration within ~5s (balanced
  threshold, per decision below)
- **review** — ambiguous, or competing hypotheses resolve to different tracks
- **miss** — no plausible candidate

Expected review volume at the balanced threshold: roughly 100–200 tracks.

### Stage 4 — review

CSV: original metadata, top 3 candidates with scores and durations, one column
to fill in. Re-runnable; only ever asks about unresolved tracks.

### Stage 5 — fingerprint

`shazamio` over stage-3 misses only (expected 10–20% of the corpus). Identifies
from the audio itself, bypassing text entirely. Results re-enter stage 3 scoring.
Survivors land in a final "not on Spotify" report rather than disappearing.

### Stage 6 — push

Create a **new public playlist**, add 100 URIs per request, skipping URIs already
present. SQLite state makes a re-run after rate-limit or crash a no-op for work
already completed. Spotify's 10,000-track playlist cap is not a constraint at 738.

## Authentication

Free Spotify developer app, Authorization Code + PKCE over a localhost redirect,
scope `playlist-modify-public`. The one-time consent click happens in Chrome
where the user is already logged in.

Driving the Spotify **web UI** to add tracks is explicitly rejected: 738 fragile
click sequences against a re-rendering SPA, versus 8 API calls.

## Error handling

- Rate limiting (HTTP 429): honor `Retry-After`, exponential backoff, resume from
  SQLite.
- Unreadable/corrupt audio: log, continue, list in the final report.
- Missing file on disk: no audio file is currently missing apart from the single
  export-failure placeholder, but the guard remains — such a track is matched on
  metadata alone and flagged as having unverifiable duration.
- Duplicates: deduped by resolved Spotify URI at push time, so the 12 known
  duplicate `performer`+`title` pairs and the 4 duplicate filenames cannot
  double-add.

## Testing

Stage 2 is pure logic with known expected outputs and is written test-first,
seeded with real messy examples drawn from the export as golden cases —
including every pattern in the contamination table above. Stages 1, 3 and 6 are
tested against recorded API fixtures, not the live service.

## Decisions

| Decision | Choice |
|---|---|
| Approach | Local Python pipeline + fingerprinting fallback |
| Video files | Skip (report only) |
| Auto-accept strictness | Balanced (~5s duration tolerance) |
| Playlist | New, public |
| Project root | `/home/arash/Downloads/Telegram Desktop/tg2spotify` |

## Risks

- **Catalog gaps.** Persian catalog on Spotify is patchy; remixes, live cuts and
  unofficial releases may not exist at all. The pipeline ends with an explicit
  not-found list rather than silently dropping tracks.
- **Wrong-version matches.** Balanced thresholds admit some risk of matching a
  remaster or alternate recording. Duration scoring mitigates but does not
  eliminate this.
- **Fingerprinting rate limits.** `shazamio` is unofficial and may throttle;
  stage 5 is resumable and non-blocking for the rest of the pipeline.
