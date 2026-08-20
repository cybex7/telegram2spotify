"""Score a Spotify search result against one hypothesis. Pure, no network.

Three signals: title similarity, artist similarity, and duration delta against
the actual file. Duration is the one signal the channel's broken tags cannot
fake, so it gates auto-acceptance rather than merely nudging the total.
"""

import difflib
import re
from dataclasses import dataclass
from typing import List, Optional

from .clean import normalize

# Recording qualifiers Spotify puts in titles that we must not reward.
_QUALIFIER = re.compile(
    r"\s*[\(\[][^\)\]]*\b(?:remaster(?:ed)?|remix|live|version|edit|mono|stereo"
    r"|deluxe|bonus|radio\s*edit|instrumental|acoustic|demo|mix)\b[^\)\]]*[\)\]]", re.I)
# Impostor recordings: these must never win silently.
_IMPOSTOR = re.compile(
    r"\b(?:karaoke|tribute|made\s+famous\s+by|in\s+the\s+style\s+of|originally"
    r"\s+performed\s+by|cover\s+version|8-?bit|lullaby|workout\s+mix)\b", re.I)
# 'with X' marks a collaboration only inside brackets -- Spotify writes
# '(with Eendo)'. Stripping a bare trailing 'with ...' would make
# 'Dancing with Myself' identical to 'Dancing'.
_FEAT_BRACKETED = re.compile(
    r"\s*[\(\[]\s*\b(?:feat|ft|featuring|with)\b\.?[^\)\]]*[\)\]]", re.I)
_FEAT_BARE = re.compile(r"\s*\b(?:feat|ft|featuring)\b\.?\s+.*$", re.I)
# Spotify's dominant convention: the qualifier trails a dash rather than sitting
# in brackets -- 'Let It Be - Remastered 2009', 'Somewhere Only We Know - Live'.
# Requiring a known keyword after the dash keeps genuine titles like
# 'Love - Hate' intact.
_DASH_QUALIFIER = re.compile(
    r"\s+-\s+[^-]*?\b(?:remaster(?:ed)?|live|version|edit|mono|stereo|deluxe"
    r"|bonus|mix|remix|instrumental|acoustic|demo|single|radio|take\s*\d+"
    r"|\d{4}\s*remaster)\b[^-]*$", re.I)
# Artists Telegram jams into one field but Spotify lists separately.
_ARTIST_SPLIT = re.compile(
    r"\s*(?:&|,|/|\bx\b|\bvs\.?\b|\bfeat\b\.?|\bft\b\.?|\bwith\b|\band\b)\s*", re.I)

AUTO_TOTAL = 0.85          # balanced threshold, per the design decision
AUTO_TITLE_SIM = 0.80
AUTO_DURATION_S = 5
# Loosened paths: perfect text on both fields is strong enough to tolerate a
# wider duration gap (a different master, not a different song), and a duration
# that matches to within 2s is strong enough to forgive a noisy title.
PERFECT_TEXT_SIM = 0.95
PERFECT_TEXT_DURATION_S = 15
TIGHT_DURATION_S = 2
TIGHT_DURATION_ARTIST_SIM = 0.85
TIGHT_DURATION_TITLE_SIM = 0.40
# Review results are published to the playlist, so 'reject' is the only quality
# gate left and has to actually catch the junk.
REJECT_TOTAL = 0.55
REJECT_DURATION_S = 60

W_TITLE, W_ARTIST, W_DURATION = 0.45, 0.35, 0.20


def _key(s: str) -> str:
    """Comparison form: normalised, qualifier-stripped, punctuation-free."""
    s = normalize(s or "")
    s = _QUALIFIER.sub("", s)
    s = _DASH_QUALIFIER.sub("", s)
    s = _FEAT_BRACKETED.sub("", s)
    s = _FEAT_BARE.sub("", s)
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip().lower()


def _sim(a: str, b: str) -> float:
    a, b = _key(a), _key(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # token-set comparison first: word order varies wildly in this corpus
    ta, tb = set(a.split()), set(b.split())
    jaccard = len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    return max(ratio, jaccard)


def _artist_sim(hyp_artist: str, cand_artists: List[str]) -> float:
    """Best similarity over every (our artist name, their artist name) pair.

    Telegram stores 'Arad Aria&Kaveh Afagh' in one field while Spotify lists two
    artists, so each side is compared piecewise as well as whole -- comparing the
    whole string too keeps names that legitimately contain a separator word
    ('Simon and Garfunkel') from being torn apart.
    """
    cands = [c for c in (cand_artists or []) if c]
    if not hyp_artist or not cands:
        return 0.0
    parts = [p for p in _ARTIST_SPLIT.split(hyp_artist) if p.strip()]
    # also a joiner-insensitive form, so 'Simon and Garfunkel' meets 'Simon & Garfunkel'
    collapsed = _ARTIST_SPLIT.sub(" ", hyp_artist)
    ours = [hyp_artist, collapsed] + parts
    joined = " ".join(c for c in cands)
    best = 0.0
    for h in ours:
        for c in cands + ([joined] if len(cands) > 1 else []):
            best = max(best, _sim(h, c))
    return best


def _duration_score(delta: Optional[float]) -> float:
    if delta is None:
        return 0.5                      # unknown: neutral, and never auto-accepts
    if delta <= 3:
        return 1.0
    if delta >= 30:
        return 0.0
    return 1.0 - (delta - 3) / 27.0


@dataclass
class Scored:
    total: float
    title_sim: float
    artist_sim: float
    duration_delta: Optional[float]
    verdict: str            # 'auto' | 'review' | 'reject'
    reason: str


def score(hyp_artist: str, hyp_title: str, cand_title: str, cand_artists: List[str],
          cand_duration_ms: Optional[int], our_duration_s: Optional[float]) -> Scored:
    title_sim = _sim(hyp_title, cand_title)
    artist_sim = _artist_sim(hyp_artist, cand_artists)

    delta: Optional[float] = None
    if cand_duration_ms and our_duration_s:
        delta = abs(cand_duration_ms / 1000.0 - our_duration_s)

    total = (W_TITLE * title_sim + W_ARTIST * artist_sim
             + W_DURATION * _duration_score(delta))

    reasons = []
    # An impostor recording the query never asked for: hard penalty.
    if _IMPOSTOR.search(cand_title or "") and not _IMPOSTOR.search(
            (hyp_title or "") + " " + (hyp_artist or "")):
        total -= 0.35
        reasons.append("impostor_recording")

    if not hyp_artist:
        reasons.append("no_artist_in_hypothesis")

    impostor = "impostor_recording" in reasons
    perfect_text = title_sim >= PERFECT_TEXT_SIM and artist_sim >= PERFECT_TEXT_SIM
    tight_duration = delta is not None and delta <= TIGHT_DURATION_S

    auto = not impostor and (
        # the original balanced path
        (total >= AUTO_TOTAL and title_sim >= AUTO_TITLE_SIM
         and delta is not None and delta <= AUTO_DURATION_S)
        # both fields exact: a wider gap means another master, not another song
        or (perfect_text and (delta is None or delta <= PERFECT_TEXT_DURATION_S))
        # the durations all but coincide: trust that over a noisy title
        or (tight_duration and artist_sim >= TIGHT_DURATION_ARTIST_SIM
            and title_sim >= TIGHT_DURATION_TITLE_SIM)
    )

    if auto:
        verdict = "auto"
    elif (impostor
          or (delta is not None and delta > REJECT_DURATION_S)
          or total < REJECT_TOTAL):
        verdict = "reject"
        if delta is not None and delta > REJECT_DURATION_S:
            reasons.append(f"duration_off_{delta:.0f}s_rejected")
    else:
        verdict = "review"
        if delta is not None and delta > AUTO_DURATION_S:
            reasons.append(f"duration_off_{delta:.0f}s")
        elif delta is None:
            reasons.append("duration_unknown")

    return Scored(round(total, 4), round(title_sim, 4), round(artist_sim, 4),
                  delta, verdict, ",".join(reasons))
