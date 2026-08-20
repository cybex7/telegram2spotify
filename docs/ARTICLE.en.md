# Moving a Telegram music archive into Spotify

I had eight and a half years of music sitting in a Telegram channel — 738 audio
files, 6.3 GB, posted between January 2018 and August 2026 — and I wanted it as
a Spotify playlist. This is what the problem actually looks like, what worked,
what Spotify refuses to let you do, and what I would tell anyone attempting it.

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

**Now the wall.** With a newly created app in Development mode, this is what
the API actually permits:

| Endpoint | Result |
|---|---|
| `GET /me` | 200 |
| `GET /me/playlists` | 200 |
| `GET /playlists/{id}` | 200 |
| `GET /tracks/{id}` (single) | 200 |
| `GET /search` | 200 (until quota) |
| `POST /users/{id}/playlists` | **403** |
| `GET /playlists/{id}/tracks` | **403** |
| `POST /playlists/{id}/tracks` | **403** |
| `GET /tracks?ids=…` (batch) | **403** |

So a new app **cannot write a playlist at all** — it cannot even read a
playlist's tracks.

Everyone's first assumption is a forgotten OAuth scope, so I recorded what
Spotify actually granted:

```
playlist-modify-private
playlist-modify-public
playlist-read-private
```

Both write scopes are present, and the writes still return 403. The
restriction is at the app level, not the scope level, and no amount of code
fixes it. If you plan an evening around
"the API will add the tracks", plan differently.

There is a second, softer wall: search quota. One 429 came back with
`Retry-After: 54879` — a **15.2 hour** ban. Do not retry against it; repeat
calls can extend it.

## Alternatives, ranked by how well they actually work

1. **An import service, fed a clean list.** Soundiiz and TuneMyMusic hold their
   own write access to Spotify and accept a pasted `Artist - Title` list. This
   is the delivery path that works today. Crucially, the pipeline above is still
   what makes it work: the importer receives Spotify's own canonical spelling
   instead of `@moozikestan_bot - …`.
2. **An older Spotify app**, created before the restrictions, may still have
   write access. Worth checking if you have one.
3. **Request extended quota** in the dashboard — a form and a review, and
   realistically not granted for hobby projects.
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

Over the first 200 tracks:

| Outcome | Count | Share |
|---|---|---|
| Matched automatically | 148 | 74% |
| Held for review (published anyway, by choice) | 27 | 13.5% |
| Not found | 25 | 12.5% |

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
  with 94 tests, all offline, every case lifted from the actual channel.
- **Make everything resumable.** Store per-track state as you go. Between rate
  limits, dead proxies and a 15-hour ban, my run was interrupted repeatedly and
  never lost work.
- **A stalled job looks exactly like a working one.** I watched process
  liveness instead of progress and lost eight hours to a job sleeping on a
  Retry-After. Poll the row count.
- **Read the API's error body.** A bare `403 Forbidden` cost a full debugging
  cycle that the response body would have ended immediately.
