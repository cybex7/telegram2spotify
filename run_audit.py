#!/usr/bin/env python3
"""Stage 4b: one combined list of everything that deserves a manual listen:

  not_found         -- status='miss', never sent to Spotify at all
  published_review  -- status='review': the scorer itself was unsure, but the
                       user chose to publish these to the playlist anyway
  weak_auto_match   -- status='matched' (auto-accepted) whose own recorded
                       scores are on the risky edge of one of score.py's three
                       accept paths (weak title text riding on duration, or
                       weak artist text riding on title+duration)

Every one of these was either not sent, or was sent without full confidence.
Rows are not re-scored -- match_reason already carries title_sim/artist_sim.
"""
import csv, os, re, sqlite3

ROOT = os.path.dirname(os.path.abspath(__file__))
con = sqlite3.connect(os.path.join(ROOT, "state.sqlite"))
con.row_factory = sqlite3.Row

ARTIST_FLOOR = 0.75
TITLE_FLOOR = 0.80

def parse(reason):
    reason = reason or ""
    m_t = re.search(r"title=([\d.]+)", reason)
    m_a = re.search(r"artist=([\d.]+)", reason)
    return (float(m_t.group(1)) if m_t else None,
            float(m_a.group(1)) if m_a else None)

def row_out(r, category, why):
    """For not_found rows, ignore any stored spotify_uri: match.py records the
    best REJECTED candidate there too, and showing it as a real track link
    would read as a match that does not exist."""
    title_sim, artist_sim = parse(r["match_reason"])
    uri = r["spotify_uri"] if category != "not_found" else None
    search_url = ("https://open.spotify.com/search/" +
                 (r["tg_performer"] or "") + " " + (r["tg_title"] or "")).replace(" ", "%20")
    return {
        "category": category,
        "why": why,
        "in_playlist": "yes" if category != "not_found" else "no",
        "msg_id": r["msg_id"],
        "title_sim": title_sim, "artist_sim": artist_sim,
        "score": r["match_score"],
        "tg_performer": r["tg_performer"] or "",
        "tg_title": r["tg_title"] or "",
        "file": r["file"] or "",
        "spotify_name": r["spotify_name"] or "" if category != "not_found" else "",
        "spotify_artists": r["spotify_artists"] or "" if category != "not_found" else "",
        "spotify_url": ("https://open.spotify.com/track/" + uri.split(":")[-1]) if uri else search_url,
    }

out = []

for r in con.execute("SELECT * FROM tracks WHERE status='miss' ORDER BY msg_id"):
    out.append(row_out(r, "not_found", "no Spotify candidate cleared the reject threshold"))

for r in con.execute("SELECT * FROM tracks WHERE status='review' AND spotify_uri IS NOT NULL ORDER BY msg_id"):
    out.append(row_out(r, "published_review",
                       "held for review by the scorer, published anyway per your call"))

for r in con.execute("SELECT * FROM tracks WHERE status='matched' AND spotify_uri IS NOT NULL ORDER BY msg_id"):
    title_sim, artist_sim = parse(r["match_reason"])
    if artist_sim is not None and artist_sim < ARTIST_FLOOR:
        out.append(row_out(r, "weak_auto_match", "artist name match is weak"))
    elif title_sim is not None and title_sim < TITLE_FLOOR:
        out.append(row_out(r, "weak_auto_match", "title match is weak (duration coincidence risk)"))

out_path = os.path.join(ROOT, "reports", "suspects.csv")
fields = ["category", "why", "in_playlist", "msg_id", "title_sim", "artist_sim", "score",
         "tg_performer", "tg_title", "file", "spotify_name", "spotify_artists", "spotify_url"]
with open(out_path, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    w.writerows(out)

by_cat = {}
for o in out:
    by_cat[o["category"]] = by_cat.get(o["category"], 0) + 1
print(f"{len(out)} rows -> {out_path}")
for cat, n in by_cat.items():
    print(f"  {cat:<20} {n}")
