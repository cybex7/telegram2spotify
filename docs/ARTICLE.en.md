# Moving a Telegram music archive into Spotify

I had eight and a half years of music sitting in a Telegram channel — 738 audio
files, posted between January 2018 and August 2026 — and I wanted it as a
Spotify playlist. Telegram's export tool offered to download 6.3 GB of audio
to get there. It turned out I barely needed any of it. This is what the problem actually looks like, what worked, the one
misdiagnosis that cost a full day, and what I would tell anyone attempting it.

Everything below is measured on that real archive, not estimated.

## The problem is not transferring files. It is names.

Spotify has no idea what an mp3 is. To put a song in a playlist you must hand it
a track id, and to get a track id you must search for an artist and a title.
So the entire job reduces to one question: **given a mangled Telegram audio
message, what is the artist and what is the title?**

Telegram stores two metadata fields on an audio message, `performer` and
`title`, separate from the file's own ID3 tags. In a channel that has been
re-forwarding music for eight years, both are unreliable in ways that are worth
enumerating, because each one breaks a different naive approach.

## Anatomy of the mess

From all 738 tracks:

| What's wrong | Tracks | Real example |
|---|---|---|
| A separator hides inside one field | 361 (48.9%) | `Ebi- Hamdam` |
| Bitrate / quality junk | 76 (10.3%) | `[320kbps]`, `[1]` |
| A channel `@handle` in a metadata field | 64 (8.7%) | `performer = @moozikestan_bot` |
| Persian script | 29 (3.9%) | `مرد تنها - فرهاد` |
| `feat.` / `ft.` variants | 22 (3.0%) | `(Feat. Britt Nicole)` |
| A website name | 19 (2.6%) | `[IstgahMusic.com]` |
| Junk in brackets | 14 (1.9%) | `{ON @Sickosadism}` |
| Leading track number in the filename | 166 | `02 Nakhosh.mp3` |

And the fields are sometimes simply absent: `performer` empty on 27 tracks
(3.7%), `title` on 18 (2.4%), **both** on 17, and duration missing on 11.

The bad news is not the missing data. It is the *confidently wrong* data:

```
performer: 'Arad Aria&Kaveh Afagh'   ← two artists jammed into one field
performer: '@jmctv♪telegram channel♪' ← a channel advertising itself as the artist
performer: '<unknown>'                ← an ID3 placeholder
performer: 'Telegram.me/melody'       ← a URL
performer: 'ludovico enaudi'          ← misspelled
performer: 'فرهاد مهراد . آیینه ها'    ← artist AND title, while `title` held a handle
```

## Why the obvious approaches fail

**Pasting titles into an importer.** Soundiiz and TuneMyMusic accept a text list
of `Artist - Title`. Feed them `@moozikestan_bot - Hafez Nazeri - Existence
Life (Rumi Symphony Project: Untold)` and you get nothing. The importers are
good; the input is poison.

**Trusting the tags.** They are wrong often enough to matter, and wrong
*silently*.

**Splitting on the dash.** This is the trap that looks solved and isn't:

```
Ebi- Hamdam            →  Ebi is the ARTIST
Kooleh- Kaveh Yaghmaei →  Kaveh Yaghmaei is the ARTIST
```

Same shape, opposite meaning. No rule operating on the string can tell them
apart. This single observation determined the whole design.

## Five sources, treated as votes

For every track I harvest five independent candidates and keep them side by
side rather than collapsing them into one "best" guess:

1. Telegram's `performer`
2. Telegram's `title`
3. The message caption
4. The filename
5. The file's own embedded ID3 tags

Source 5 matters more than you'd expect: Telegram's attributes and the file's
ID3 frequently disagree, and ID3 is sometimes the correct one. I recovered
usable tags from 622 of the files. (I wrote a ~60-line ID3v2 reader because the
machine had no `pip`; `mutagen` does this properly if you can install it.)

## The cleaning rules that actually earn their place

Order matters. Every rule below exists because a real track needed it.

**1. Normalise Persian orthography first.** Farsi text is routinely typed with
Arabic letters: `ي→ی`, `ك→ک`, `ة→ه`, plus Arabic-Indic digits and ZWNJ. Without
this fold, two spellings of the same artist never compare equal.

**2. Judge brackets, don't strip them.** This is where naive cleaners destroy
data. These must go:

```
{ON @Sickosadism}   [IstgahMusic.com]   [320kbps]   [1]   ( Compiled By PrOmid )
```

These must stay:

```
(feat. Eendo)   (Rumi Symphony Project: Untold)
```

So the rule inspects the bracket *contents* for spam signals — an `@`, a
domain, `kbps`, `compiled by`, or nothing but digits — and only then deletes.

**3. Strip leading track numbers, with a guard.** `02 Nakhosh` and
`15. The Last Man` need the number gone. `50 Cent`, `2 Unlimited` and
`30 Seconds To Mars` must survive. The rule that separates them: strip only if
punctuation follows the digits, **or** the number is zero-padded. This fired on
159 tracks, mostly via filenames.

**4. Delete what's left of a channel's branding.** Removing `@jmctv` from
`@jmctv♪telegram channel♪` leaves `♪telegram channel♪`, which then got used as
the artist name and outranked the correct guess. The fix is a gate that removes
noise words (`telegram`, `channel`, `bot`, …) plus decoration and asks whether
anything meaningful remains. `Channel Orange` keeps its `Orange` and survives;
`♪telegram channel♪` doesn't.

**5. Recognise placeholders.** `<unknown>`, `Unknown Artist`, `Various
Artists` are not performers. But `Unknown Mortal Orchestra` is a real band, so
the check is exact-match on a small set, not substring.

**6. Handle filename conventions.** Underscores become spaces, trailing
download ids go (`King-Raam-The-Last-Waltz_3136300`), and extensions are
stripped by known audio suffix — because three files carried mangled ones like
`.mp3 x-amz-content-sh`.

**7. Split multi-artist fields.** `Arad Aria&Kaveh Afagh` scored 0.125 against
Spotify's separately-listed artists. Compare the name whole, piecewise, **and**
with joiners collapsed, so `Simon and Garfunkel` also meets `Simon & Garfunkel`.

## The central idea: generate hypotheses, don't make decisions

Because no rule can tell `Ebi- Hamdam` from `Kooleh- Kaveh Yaghmaei`, the
cleaner never decides. It emits a ranked set of `(artist, title)` guesses and
lets Spotify's catalogue arbitrate:

| # | Hypothesis | Catches |
|---|---|---|
| H1 | cleaned performer + cleaned title | the well-tagged majority |
| H2 | the two fields swapped | `performer` held both, `title` held a handle |
| H3/H4 | split a field on its separator, **both orders** | the undecidable dash |
| H5 | the same splits on the filename | the 17 tracks with no tags at all |
| H6 | the file's ID3 tags | when Telegram's attributes are worse |
| H7 | title alone, no artist constraint | last resort |

That produced 2,839 hypotheses for 738 tracks — 3.8 per track. The asymmetry
is what makes this safe: **a wrong guess costs one wasted search, a wrong
decision costs a wrong song in your playlist.**

Which hypothesis actually won, among the tracks that matched:

```
performer+title      149   (87%)
title:split           10
filename:split         4
id3                    3
swapped                2
title:paren            2
title:bare             2
...
```

Read that carefully. Most tracks were fine with their plain tags — but 13%
needed a fallback, and those are exactly the tracks a naive script loses
silently.

## Scoring: duration is the only honest signal

Each candidate gets three scores: title similarity, artist similarity, and
**duration difference against the actual file**.

That third one carries disproportionate weight, and here's why: the tags can
lie about names, but the file's length cannot. So duration doesn't merely nudge
the score — it *gates* automatic acceptance. Two real cases:

- `The Beatles - Let It Be` — title similarity only 0.667, duration off by
  **0.17 seconds**. Obviously correct.
- `Hafez Nazeri - Existence Life (Rumi Symphony Project: Untold)` — title
  similarity 0.49 because our title carried the project name, duration off by
  **0.08 seconds**. Correct.

Conversely, `Cigarettes After Sex - Apocalypse` matched on title and artist
exactly but was 40 seconds apart — a different version, held back for review.

## Three Spotify-side traps

**Dash-suffix qualifiers.** Spotify writes `Let It Be - Remastered 2009`, not
`Let It Be (Remastered 2009)`. I stripped only bracketed qualifiers at first,
so The Beatles scored 0.667 and went to manual review despite a 0.17s duration
match. Strip after a dash too — but require a known keyword (`remastered`,
`live`, `radio edit`, …) so a genuine title like `Love - Hate` survives.

**Impostor recordings.** Karaoke versions, tribute bands and "made famous by"
covers match text beautifully. They need an explicit penalty, and if you're
publishing unreviewed matches they need outright rejection.

**`with` is only a collaboration marker inside brackets.** I stripped bare
`with …` from titles, which made `Dancing with Myself` identical to `Dancing`.
Bracketed only.

## The Spotify app, and the wall you will hit

Getting credentials is easy and free. Create an app at
`developer.spotify.com/dashboard`, set the redirect URI to
`http://127.0.0.1:8888/callback`, and use **Authorization Code with PKCE** —
which needs only the client id, a public identifier. You never handle a client
secret. A tiny local HTTP server catches the redirect.

One implementation detail costs an hour if you miss it: serve the callback
until the *real* redirect arrives. Chrome also requests `/favicon.ico`, and a
one-shot handler spends itself on that and then hangs.

**Now the wall — and the way through it.** With a newly created app in
Development mode, several endpoints return `403 Forbidden`. Here is what the API
actually permits:

| Endpoint | Result |
|---|---|
| `GET /me` | 200 |
| `GET /me/playlists` | 200 |
| `GET /playlists/{id}` | 200 |
| `GET /tracks/{id}` (single) | 200 |
| `GET /search` | 200 (until quota) |
| `PUT /playlists/{id}` (edit details) | 200 |
| `GET /playlists/{id}/items` | 200 |
| **`POST /playlists/{id}/items`** | **200 — this is how you write** |
| `GET|POST /playlists/{id}/tracks` | **403** |
| `POST|GET /users/{id}/playlists` | **403** |
| `GET /tracks?ids=…` (batch) | **403** |

Read those last three rows against the ones above them. `/playlists/{id}/tracks`
is 403 while `/playlists/{id}/items` is 200 — **the same playlist, the same
token, the same scopes.** The `/tracks` sub-resource is retired for new apps.
The `/items` sub-resource is its live replacement. That is the whole story, and
it took me a day to see it.

I want to be honest about how I got it wrong, because the mistake is the useful
part. I saw `403 Forbidden` on every playlist write, checked that the scopes
were granted:

```
playlist-modify-private
playlist-modify-public
playlist-read-private
```

…and concluded that the restriction must be at the app level — Spotify banning
Development-mode apps from playlist writes. It was a coherent theory. It
explained every observation I had. I wrote it into the documentation, designed a
whole fallback delivery path around it, and started investigating whether the
*library* endpoints might be writable instead.

The theory was wrong, and two cheap calls would have refuted it:

- **`PUT /playlists/{id}`** — editing a playlist's description requires
  `playlist-modify-public`, exactly like adding tracks. It returned **200**. So
  playlist write permission was working the entire time. A ban on writes that
  permits a write is not a ban.
- **`GET /playlists/{id}`** — the playlist object Spotify handed back contained
  a link to its own contents, and that link read
  `…/playlists/{id}/items?offset=0&limit=0`. **Not `/tracks`.** The API had been
  telling me the correct path in every response I had already received.

The lesson generalizes past Spotify. `403 Forbidden` with no detail is not a
diagnosis, it is the absence of one. A generic error is compatible with many
theories, and the instinct to accept the first coherent one is exactly what you
have to resist. The question to ask is not "does my theory explain what I see?"
but **"what call would come out differently if my theory were wrong?"** — then
make that call. I skipped that step and paid a day for it.

One more trap follows immediately, and it fails *silently*: on `/items`, each
entry's payload field is named `item`. On the retired `/tracks` it was `track`.
My de-duplication read `item.track.uri`, got `None` for everything, concluded
the playlist was empty, and would have cheerfully re-added all 174 tracks on
every run. A 403 shouts. This just quietly returns the wrong answer, which is
worse. Both the path and the field name are now pinned by tests.

There is a second, genuinely hard wall: search quota. One 429 came back with
`Retry-After: 54879` — a **15.2 hour** ban. Do not retry against it; repeat
calls can extend it.

## Alternatives, ranked by how well they actually work

1. **The API itself, via `POST /playlists/{id}/items`.** This is the delivery
   path, and it needs nothing but a free app and a client id. Everything below
   is a fallback for cases where it genuinely is not available to you.
2. **An import service, fed a clean list.** Soundiiz and TuneMyMusic hold their
   own write access and accept a pasted `Artist - Title` list. Worth knowing
   about, and worth noting that the pipeline above is what makes it work: the
   importer receives Spotify's own canonical spelling instead of
   `@moozikestan_bot - …`. But it is a manual hop you probably do not need.
3. **Request extended quota** in the dashboard — a form and a review, and
   realistically not granted for hobby projects. Relevant to search volume, not
   to writes.
4. **Audio fingerprinting** (`shazamio`, AcoustID/Chromaprint) identifies a
   track from the audio itself, ignoring text entirely. This is the right tool
   for files whose tags are hopeless, and it sidesteps transliteration
   completely. I built it as an optional stage and never needed it, because
   text matching left few enough misses.
5. **MusicBrainz or Last.fm** as a canonicalisation step before searching
   Spotify — useful if you want artist names normalised against a real database
   rather than heuristics.
6. **Manual, but assisted.** Emit an `open.spotify.com/search/<query>` link per
   unmatched track. One click each. Fine for tens, not hundreds.
7. **Telethon** instead of Telegram Desktop's export if you want the channel
   pulled programmatically.

## Results, honestly

All 738 tracks, final:

| Outcome | Count | Share |
|---|---|---|
| Matched automatically | 596 | 80.8% |
| Held for review (published anyway, by choice) | 64 | 8.7% |
| Not found | 78 | 10.6% |

**642 unique tracks are in the playlist**, written directly by the API — 660
matched-or-review rows collapse to 642 URIs because of the corpus's 12
duplicate performer+title pairs and 4 duplicate filenames, exactly as the
de-duplication was designed to handle. Verified against the live playlist
afterward: 0 missing, 0 extra, 0 orphans.

It took three passes across roughly a day and a half, entirely because of
search quota, not code: three 429 bans (15.2h, 23.8h, 23.9h) set the pace.
Matching costs roughly 4 searches per track against a ban that allows perhaps
600 searches per window — so budget multiple windows, not one run, if your
catalog is in the hundreds.

One measurement that changed the design mid-run: re-trying tracks that already
failed is almost pure waste. 52 previously-unresolved tracks consumed 353
searches — more than half a quota window — and converted exactly one.
Re-trying them is opt-in behind a flag now, for after the cleaning rules
change, not before. The 78 that never matched are Telegram's genuine catalog
gaps — under the 100-track manual threshold set at the start, each with a
ready search link in `reports/not_found.csv`.

52 of the matched tracks had their artist tag *corrected* — the Telegram tag
was wrong, and duration plus title found the truth. Some pleasing ones:

```
'ludovico enaudi'            → Ludovico Einaudi, Royal Philharmonic Orchestra
'<unknown>'                  → Billie Eilish
'@jmctv♪telegram channel♪'   → Ebi
'Telegram.me/melody'         → Ebi — Atreh Toh   (transliteration differed too)
'Angus And Julia Stone'      → Angus & Julia Stone
```

And one failure worth more than the successes. This track:

```
performer: 'Arad Aria&Kaveh Afagh'
title:     'While my guitar gently weeps'
```

matched to **George Harrison, live from Madison Square Garden, 1971**. It is a
Persian cover, and the pipeline confidently found the English original. Nothing
in the metadata says "cover", the title is a perfect match, and the durations
were close enough. Text matching cannot see this. Fingerprinting the audio
would have caught it.

That is the honest limit of the whole approach: it identifies *songs*, not
*recordings*. If you care which recording, budget for review — or fingerprint.

## What I would tell you before you start

- **Run against real data on day one.** Every genuine bug here was found by
  running the thing, not by reading the code: the dash-suffix qualifiers, the
  surviving channel branding, the multi-artist fields, the bare `with`. A
  20-track sample found four defects that no amount of design would have.
- **Pin each defect with a test using the real string that broke it.** I ended
  with 100 tests, all offline, every case lifted from the actual channel — and
  six of them exist purely to stop a future session from reverting to the
  retired API path.
- **Make everything resumable.** Store per-track state as you go. Between rate
  limits, dead proxies and a 15-hour ban, my run was interrupted repeatedly and
  never lost work.
- **A stalled job looks exactly like a working one.** I watched process
  liveness instead of progress and lost eight hours to a job sleeping on a
  Retry-After. Poll the row count.
- **Read the API's error body** — and do not stop there. A generic
  `403 Forbidden` is not a diagnosis. Before you accept a theory, name the call
  whose result would differ if the theory were false, and make that call. Mine
  was `PUT /playlists/{id}`; it took thirty seconds and it would have saved a
  day.
- **Read the responses you already have.** Spotify had been returning the
  correct endpoint path inside every playlist object I fetched. The answer was
  sitting in data I had printed and not looked at.
- **Distrust the errors that do not shout.** The retired path returned 403 and
  I noticed within seconds. The renamed `track` → `item` field returned an empty
  list, which read as "the playlist is empty" and would have silently duplicated
  every track. Silent wrong answers cost more than loud failures.
- **You almost certainly do not need to download the audio.** Telegram's JSON
  export already carries `performer`, `title`, the caption, the filename, and
  (for 727 of 738 tracks here) the duration. The one thing that genuinely
  requires the file — its own ID3 tags, read as a fifth independent vote — only
  ended up deciding the *winning* match for **4 of 660** successful matches.
  Drag Telegram Desktop's export size-limit slider to the minimum and skip
  gigabytes of downloading; the pipeline already treats a missing file as a
  normal case, not an error, so nothing else changes.
