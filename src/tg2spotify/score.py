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
_FEAT_PART = re.compile(r"\s*[\(\[]?\s*\b(?:feat|ft|featuring|with)\b\.?[^\)\]]*[\)\]]?", re.I)

AUTO_TOTAL = 0.85          # balanced threshold, per the design decision
AUTO_TITLE_SIM = 0.80
AUTO_DURATION_S = 5
REJECT_TOTAL = 0.45

W_TITLE, W_ARTIST, W_DURATION = 0.45, 0.35, 0.20


def _key(s: str) -> str:
    """Comparison form: normalised, qualifier-stripped, punctuation-free."""
    s = normalize(s or "")
    s = _QUALIFIER.sub("", s)
    s = _FEAT_PART.sub("", s)
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
    artist_sim = max((_sim(hyp_artist, a) for a in (cand_artists or [])), default=0.0)

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

    if (total >= AUTO_TOTAL and title_sim >= AUTO_TITLE_SIM
            and delta is not None and delta <= AUTO_DURATION_S
            and "impostor_recording" not in reasons):
        verdict = "auto"
    elif total < REJECT_TOTAL:
        verdict = "reject"
    else:
        verdict = "review"
        if delta is not None and delta > AUTO_DURATION_S:
            reasons.append(f"duration_off_{delta:.0f}s")
        elif delta is None:
            reasons.append("duration_unknown")

    return Scored(round(total, 4), round(title_sim, 4), round(artist_sim, 4),
                  delta, verdict, ",".join(reasons))
