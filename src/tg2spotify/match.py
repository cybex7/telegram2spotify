"""Stage 3 — resolve each track against the Spotify catalogue.

Walks a track's hypotheses in confidence order and stops at the first that
auto-accepts, so well-tagged tracks cost one search and only the messy ones
cost several. Every outcome is written to SQLite, so an interrupted run
resumes without repeating work.
"""

import csv
import os
import urllib.parse
from typing import Dict, List, Optional

from .api import RateLimited
from .score import score


def _our_duration(row) -> Optional[float]:
    if row["duration_tg"]:
        return float(row["duration_tg"])
    if row["id3_length_ms"]:
        return float(row["id3_length_ms"]) / 1000.0
    return None


def _queries(artist: str, title: str) -> List[str]:
    """Field-qualified query first, then a loose one as a fallback."""
    out = []
    if artist and title:
        out.append(f'track:"{title}" artist:"{artist}"')
        out.append(f"{artist} {title}")
    elif title:
        out.append(f'track:"{title}"')
        out.append(title)
    return out


def run(con, api, limit: Optional[int] = None, verbose: bool = True) -> Dict[str, int]:
    todo = con.execute(
        "SELECT * FROM tracks WHERE status IN ('ingested','review','miss') ORDER BY msg_id"
    ).fetchall()
    if limit:
        todo = todo[:limit]

    stats = {"auto": 0, "review": 0, "miss": 0, "searches": 0}
    # A network outage makes every search raise, which would otherwise be
    # recorded as "not on Spotify" for all 738 tracks -- a plausible-looking
    # result that is entirely wrong. Abort instead.
    dead_streak = 0
    DEAD_STREAK_LIMIT = 10

    for i, row in enumerate(todo, 1):
        mid = row["msg_id"]
        ours = _our_duration(row)
        hyps = con.execute(
            "SELECT * FROM hypotheses WHERE msg_id=? ORDER BY rank", (mid,)).fetchall()

        best = None
        best_hyp = None
        searched_ok = False
        for h in hyps:
            for q in _queries(h["artist"], h["title"]):
                try:
                    items = api.search_tracks(q, limit=5)
                except RateLimited:
                    # Stop immediately: retrying a banned endpoint can extend
                    # the ban, and everything so far is already committed.
                    raise
                except Exception as exc:
                    if verbose:
                        print(f"  #{mid} search failed: {exc}")
                    items = []
                else:
                    searched_ok = True
                stats["searches"] += 1
                for it in items:
                    s = score(h["artist"], h["title"], it.get("name") or "",
                              [a.get("name") for a in (it.get("artists") or [])],
                              it.get("duration_ms"), ours)
                    if best is None or s.total > best[0].total:
                        best, best_hyp = (s, it), h
                if items:
                    break                      # loose fallback only when strict found nothing
            if best and best[0].verdict == "auto":
                break                          # good enough; stop burning calls

        if best and best[0].verdict == "auto":
            status = "matched"
            stats["auto"] += 1
        elif best and best[0].verdict == "review":
            status = "review"
            stats["review"] += 1
        else:
            status = "miss"
            stats["miss"] += 1

        s, item = (best if best else (None, None))
        con.execute("""UPDATE tracks SET status=?, spotify_uri=?, match_score=?,
                       match_reason=? WHERE msg_id=?""",
                    (status,
                     (item or {}).get("uri"),
                     s.total if s else None,
                     (f"{s.verdict}|title={s.title_sim}|artist={s.artist_sim}"
                      f"|dur={s.duration_delta}|{s.reason}"
                      f"|hyp={best_hyp['source']}" if s else "no_candidate"),
                     mid))
        con.commit()

        if searched_ok:
            dead_streak = 0
        else:
            dead_streak += 1
            if dead_streak >= DEAD_STREAK_LIMIT:
                raise RuntimeError(
                    f"network looks down: {dead_streak} consecutive tracks had every "
                    f"search fail. Stopping so the remaining tracks are not recorded "
                    f"as 'not on Spotify'. Fix connectivity and re-run -- progress so "
                    f"far is saved.")

        if verbose and (i % 25 == 0 or i == len(todo)):
            print(f"  {i}/{len(todo)}  auto={stats['auto']} "
                  f"review={stats['review']} miss={stats['miss']} "
                  f"searches={stats['searches']}")

    return stats


def _search_url(artist: str, title: str) -> str:
    return "https://open.spotify.com/search/" + urllib.parse.quote(
        f"{artist} {title}".strip())


def write_reports(con, report_dir: str) -> Dict[str, int]:
    """review.csv for the ambiguous, not_found.csv for the manual pile."""
    os.makedirs(report_dir, exist_ok=True)
    counts = {}

    review = con.execute(
        "SELECT * FROM tracks WHERE status='review' ORDER BY match_score DESC").fetchall()
    with open(os.path.join(report_dir, "review.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["msg_id", "tg_performer", "tg_title", "best_guess_artist",
                    "best_guess_title", "duration_s", "score", "why",
                    "candidate_uri", "spotify_search", "keep? (y/n)"])
        for r in review:
            w.writerow([r["msg_id"], r["tg_performer"], r["tg_title"],
                        r["clean_artist"], r["clean_title"],
                        r["duration_tg"], r["match_score"], r["match_reason"],
                        r["spotify_uri"],
                        _search_url(r["clean_artist"] or "", r["clean_title"] or ""), ""])
    counts["review"] = len(review)

    miss = con.execute("SELECT * FROM tracks WHERE status='miss' ORDER BY msg_id").fetchall()
    with open(os.path.join(report_dir, "not_found.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["msg_id", "artist", "title", "duration_s", "tg_performer",
                    "tg_title", "filename", "spotify_search_url"])
        for r in miss:
            w.writerow([r["msg_id"], r["clean_artist"], r["clean_title"],
                        r["duration_tg"], r["tg_performer"], r["tg_title"],
                        os.path.basename(r["file"] or ""),
                        _search_url(r["clean_artist"] or "", r["clean_title"] or "")])
    counts["not_found"] = len(miss)
    return counts
