"""Repair Telegram audio metadata and turn it into searchable guesses.

Two responsibilities, both pure (no I/O, no network):

  clean_field()      one contaminated string -> one clean string + rules fired
  build_hypotheses() a track's raw fields    -> ranked (artist, title) guesses

The design principle: this module never *decides* which side of a separator is
the artist. `Ebi- Hamdam` is Artist-Title while `Kooleh- Kaveh Yaghmaei` is
Title-Artist, and nothing in the string distinguishes them. So both readings
are emitted and Spotify's catalogue arbitrates. A wrong guess costs one wasted
search; a wrong *decision* would cost a wrong song in the playlist.
"""

import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# --------------------------------------------------------------- normalisation

# Arabic letters that Persian text is routinely (mis)typed with. Without this
# folding, two spellings of the same artist never compare equal.
_FOLD = {
    "ي": "ی",  # ARABIC YEH        -> FARSI YEH
    "ى": "ی",  # ALEF MAKSURA      -> FARSI YEH
    "ك": "ک",  # ARABIC KAF        -> KEHEH
    "ة": "ه",  # TEH MARBUTA       -> HEH
    "ۀ": "ه",  # HEH WITH YEH ABOVE-> HEH
    "أ": "ا",  # ALEF WITH HAMZA   -> ALEF
    "إ": "ا",
    "ٱ": "ا",
}
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩"
                        "۰۱۲۳۴۵۶۷۸۹",
                        "01234567890123456789")
# bidi controls and BOM: invisible, but they break exact comparison
_INVISIBLE = dict.fromkeys(
    map(ord, "‎‏‪‫‬‭‮⁦⁧⁨⁩﻿"), None)

AUDIO_EXT = ("mp3", "m4a", "mp4", "flac", "ogg", "oga", "opus", "wav", "aac", "wma", "aiff")


def normalize(s: str) -> str:
    """Unicode-normalise, fold Persian orthography, unify digits and spaces."""
    s = unicodedata.normalize("NFKC", s)
    s = s.translate(_INVISIBLE).translate(_DIGITS)
    s = s.replace("‌", " ")                      # ZWNJ -> space, for search
    s = "".join(_FOLD.get(ch, ch) for ch in s)
    return re.sub(r"\s+", " ", s).strip()


# ------------------------------------------------------------------ spam rules

_HANDLE = re.compile(r"@[\w؀-ۿ]+")
_URL = re.compile(r"https?://\S+", re.I)
_DOMAIN = re.compile(
    r"\b(?:www\.)?[\w\-]{2,}\.(?:com|net|org|ir|info|me|co|tv|xyz|biz|ru|io|music)\b", re.I)
_BITRATE = re.compile(r"\b\d{2,3}\s*kbps\b", re.I)
_BRACKET = re.compile(r"[\(\[\{]([^\(\)\[\]\{\}]*)[\)\]\}]")

# What makes a bracketed group junk rather than real title information.
# `(feat. Eendo)` and `(Rumi Symphony Project: Untold)` must survive this.
_BRACKET_SPAM = re.compile(
    r"(?:@|www\.|https?://|\.(?:com|ir|net|org)\b|kbps|\bon\s+@|\bcompiled\s+by\b"
    r"|\btelegram\b|\bchannel\b|\bofficial\s+(?:video|audio|music\s*video)\b"
    r"|^\s*\d{1,4}\s*$)", re.I)

# A leading number is a track number only if punctuation follows it, or it is
# zero-padded. Guards real artist names: `50 Cent`, `2 Unlimited`.
_TRACKNUM = re.compile(r"^(0\d|\d{1,2})\s*(?:([.\-_)\]])\s*|\s+)")

_EDGE_JUNK = re.compile(r"^[\s\-–—.,|/_:]+|[\s\-–—,|/_:]+$")

# Words that identify a Telegram channel rather than a musician. Used only to
# test whether ANYTHING meaningful is left; 'Channel Orange' keeps its 'Orange'
# and therefore survives.
_NOISE_WORDS = re.compile(r"\b(?:telegram|channel|chanel|kanal|group|admin|bot|music)\b", re.I)


# Values tag editors write when they have nothing: never a real performer.
_PLACEHOLDERS = {"unknown", "unknown artist", "various", "various artists", "va",
                 "n/a", "na", "none", "no artist", "untitled", "track", "audio"}


def _is_placeholder(s: str) -> bool:
    return re.sub(r"[^\w\s]", "", s, flags=re.UNICODE).strip().lower() in _PLACEHOLDERS


def _is_only_noise(s: str) -> bool:
    """True when a field holds nothing but channel branding or decoration."""
    core = _NOISE_WORDS.sub(" ", s)
    core = re.sub(r"[^\w]+", " ", core, flags=re.UNICODE).strip()
    return not core


@dataclass
class Cleaned:
    text: str
    rules: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.text)


def clean_field(raw: Optional[str]) -> Cleaned:
    """Strip channel spam from one metadata field, logging every rule that fired."""
    if not raw:
        return Cleaned("")
    rules: List[str] = []
    s = normalize(str(raw))

    # Brackets are judged before bare handles are removed, so that the evidence
    # inside them ("ON @foo", "compiled by") is still there to judge.
    def _judge(m: "re.Match[str]") -> str:
        inner = m.group(1)
        if _BRACKET_SPAM.search(inner):
            rules.append("bracket_spam")
            return " "
        return m.group(0)

    s = _BRACKET.sub(_judge, s)

    for pattern, rule in ((_URL, "url"), (_DOMAIN, "domain"),
                          (_HANDLE, "handle"), (_BITRATE, "bitrate")):
        s, n = pattern.subn(" ", s)
        if n:
            rules.append(rule)

    s = re.sub(r"\s+", " ", s).strip()

    m = _TRACKNUM.match(s)
    if m and (m.group(2) or m.group(1).startswith("0")):
        s = s[m.end():]
        rules.append("track_number")

    s = _EDGE_JUNK.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()

    if s and _is_placeholder(s):
        rules.append("placeholder")
        s = ""
    elif s and _is_only_noise(s):
        rules.append("channel_noise")
        s = ""
    return Cleaned(s, rules)


# ------------------------------------------------------------------- feat / by

_FEAT = re.compile(
    r"\s*[\(\[]?\s*\b(?:feat|ft|featuring|with)\b\.?\s+([^\(\)\[\]]+?)\s*[\)\]]?\s*$", re.I)


def extract_feat(s: Optional[str]) -> Tuple[str, Optional[str]]:
    """Split a trailing 'feat. X' off a string. Spotify's canonical titles are
    inconsistent about including it, so callers search both forms."""
    if not s:
        return "", None
    s = s.strip()
    m = _FEAT.search(s)
    if not m:
        return s, None
    body = s[:m.start()].strip(" ([-–—,")
    return (body or s), m.group(1).strip()


# -------------------------------------------------------------------- splitting

# Ordered by how reliably each separator marks an artist/title boundary.
_SEPARATORS = (
    r"\s+[-–—]\s+",           # Hafez Nazeri - Existence Life
    r"\s+\.\s+",              # Persian convention: Ghad boland . Korosh yaghmaei
    r"\s+[|/]\s+",
    r"(?<=\S)[-–—]\s+",       # Ebi- Hamdam
    r"\s+[-–—](?=\S)",        # Ebi -Hamdam
    r"(?<=\w)[-–—](?=\w)",    # Damahi-Niaz
    r"(?<=\w)[|/](?=\w)",     # queen/Something
)


def split_pairs(s: Optional[str]) -> List[Tuple[str, str]]:
    """Every plausible (left, right) division of a string, best separator first.

    Returns [] when nothing looks like a separator. Over-splitting is cheap
    (one wasted search); under-splitting loses the track entirely.
    """
    if not s:
        return []
    out: List[Tuple[str, str]] = []
    for pattern in _SEPARATORS:
        m = re.search(pattern, s)
        if not m:
            continue
        left, right = s[:m.start()].strip(), s[m.end():].strip()
        if len(left) >= 2 and len(right) >= 2 and (left, right) not in out:
            out.append((left, right))
    return out


def filename_stem(name: Optional[str]) -> str:
    """Strip the extension, including the malformed ones in this export
    (`.mp3 x-amz-content-sh`, trailing `.)`)."""
    if not name:
        return ""
    base = os.path.basename(str(name))
    m = re.search(r"\.(?:%s)\b.*$" % "|".join(AUDIO_EXT), base, re.I)
    stem = base[:m.start()] if m else re.sub(r"\.[A-Za-z0-9]{2,5}$", "", base)
    stem = stem.replace("_", " ")                      # download convention
    stem = re.sub(r"\s+\d{5,}$", "", stem)              # trailing site id
    return re.sub(r"\s+", " ", stem).strip()


# ------------------------------------------------------------------ hypotheses

@dataclass
class Hypothesis:
    artist: str
    title: str
    source: str
    confidence: float = 0.5


MAX_HYPOTHESES = 8

_TRAILING_PAREN = re.compile(r"^(.*?\S)\s*[\(\[]([^\(\)\[\]]{2,40})[\)\]]\s*$")
# qualifiers that describe the recording, not the performer
_NOT_AN_ARTIST = re.compile(
    r"^\s*(?:feat|ft|featuring|with|remix|live|version|mix|edit|instrumental"
    r"|acoustic|cover|prod|remaster|radio|original|demo|bonus)\b", re.I)


def build_hypotheses(
    performer: Optional[str] = None,
    title: Optional[str] = None,
    filename: Optional[str] = None,
    caption: Optional[str] = None,
    id3_artist: Optional[str] = None,
    id3_title: Optional[str] = None,
    cap: int = MAX_HYPOTHESES,
) -> List[Hypothesis]:
    """Ranked, de-duplicated (artist, title) guesses for one track."""
    perf = clean_field(performer).text
    titl = clean_field(title).text
    stem = clean_field(filename_stem(filename)).text
    cap_txt = clean_field(caption).text
    i3a = clean_field(id3_artist).text
    i3t = clean_field(id3_title).text

    out: List[Hypothesis] = []
    seen = set()

    def add(artist: str, ttl: str, source: str, confidence: float) -> None:
        artist, ttl = artist.strip(), ttl.strip()
        if not ttl or (artist, ttl) in seen:
            return
        seen.add((artist, ttl))
        out.append(Hypothesis(artist, ttl, source, confidence))

    # 1. the fields as Telegram recorded them
    if perf and titl:
        add(perf, titl, "performer+title", 0.9)
    # 2. the file's own tags: an independent vote, often better than Telegram's
    if i3a and i3t:
        add(i3a, i3t, "id3", 0.85)
    # 3. the two fields swapped (perf held 'Artist . Title', title held a handle)
    if perf and titl:
        add(titl, perf, "swapped", 0.5)
    # 4. separators inside each field, both directions
    for src, text, base in (("title", titl, 0.7), ("performer", perf, 0.6),
                            ("filename", stem, 0.55), ("caption", cap_txt, 0.4)):
        for left, right in split_pairs(text):
            add(left, right, f"{src}:split", base)
            add(right, left, f"{src}:split_rev", base - 0.15)
    # 5. the artist sometimes hides in a trailing parenthetical
    for src, text in (("title", titl), ("filename", stem)):
        m = _TRAILING_PAREN.match(text or "")
        if m and not _NOT_AN_ARTIST.match(m.group(2)):
            add(m.group(2).strip(), m.group(1).strip(), f"{src}:paren", 0.45)
    # 6. whole strings with no artist constraint: Spotify's own relevance ranking
    for src, text in (("title", titl), ("filename", stem), ("performer", perf)):
        if text:
            add("", text, f"{src}:bare", 0.3)
            break

    out.sort(key=lambda h: -h.confidence)
    return out[:cap]
