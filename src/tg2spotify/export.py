"""Export matched tracks in a form a human or an import service can consume.

Playlist writes now work directly (POST /playlists/{id}/items), so this stage is
no longer the delivery path -- it is kept as a readable record of what matched
and as a fallback for anyone whose app cannot write playlists.

The lines are plain "Artist - Title", and by this point that text is Spotify's
own canonical spelling rather than the channel's mangled tags, which is the
whole point of the pipeline. Soundiiz and TuneMyMusic consume it as-is.
"""

import csv
import os
import re
from typing import Dict, List, Optional

# Importers match plain names; a trailing '- Remastered 2009' only hurts.
_TAIL_QUALIFIER = re.compile(
    r"\s+-\s+[^-]*?\b(?:remaster(?:ed)?|live|version|edit|mono|stereo|deluxe"
    r"|bonus|mix|remix|instrumental|acoustic|demo|single|radio)\b[^-]*$", re.I)


def import_line(artist: str, title: str) -> str:
    """One 'Artist - Title' line for a text import."""
    title = _TAIL_QUALIFIER.sub("", (title or "").strip())
    artist = (artist or "").split(",")[0].strip()
    return f"{artist} - {title}".strip(" -")


def track_url(uri: str) -> str:
    return "https://open.spotify.com/track/" + (uri or "").split(":")[-1]


def ensure_columns(con) -> None:
    have = {r[1] for r in con.execute("PRAGMA table_info(tracks)")}
    for col in ("spotify_name", "spotify_artists", "spotify_album"):
        if col not in have:
            con.execute(f"ALTER TABLE tracks ADD COLUMN {col} TEXT")
    con.commit()


def fetch_canonical(con, api, verbose: bool = True) -> Dict[str, int]:
    """Fill in Spotify's own names, one track per request.

    The batch endpoint (/tracks?ids=) is 403 for this app; single lookups are
    permitted, so 173 tracks cost 173 paced requests. Resumable: rows already
    filled in are skipped.
    """
    ensure_columns(con)
    rows = con.execute("""SELECT msg_id, spotify_uri FROM tracks
                          WHERE spotify_uri IS NOT NULL
                            AND status IN ('matched','review')
                            AND (spotify_name IS NULL OR spotify_name='')
                          ORDER BY msg_id""").fetchall()
    stats = {"fetched": 0, "failed": 0}
    for i, row in enumerate(rows, 1):
        uri = row[1]
        try:
            t = api._request("GET", "/tracks/" + uri.split(":")[-1])
        except Exception as exc:
            stats["failed"] += 1
            if verbose:
                print(f"  {uri}: {exc}")
            continue
        con.execute("""UPDATE tracks SET spotify_name=?, spotify_artists=?,
                       spotify_album=? WHERE msg_id=?""",
                    (t.get("name"),
                     ", ".join(a["name"] for a in (t.get("artists") or [])),
                     (t.get("album") or {}).get("name"),
                     row[0]))
        con.commit()
        stats["fetched"] += 1
        if verbose and i % 25 == 0:
            print(f"  {i}/{len(rows)} canonical names fetched")
    return stats


def write_import_files(con, report_dir: str) -> Dict[str, int]:
    os.makedirs(report_dir, exist_ok=True)
    rows = con.execute("""SELECT DISTINCT spotify_uri, spotify_name, spotify_artists,
                                 spotify_album, status
                          FROM tracks
                          WHERE spotify_uri IS NOT NULL
                            AND status IN ('matched','review')
                          ORDER BY spotify_artists, spotify_name""").fetchall()

    seen, lines, csv_rows = set(), [], []
    for uri, name, artists, album, status in rows:
        if uri in seen:
            continue
        seen.add(uri)
        line = import_line(artists or "", name or "")
        if line and line != "-":
            lines.append(line)
        csv_rows.append([artists or "", name or "", album or "",
                         track_url(uri), uri, status])

    with open(os.path.join(report_dir, "import_list.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(os.path.join(report_dir, "import_list.csv"), "w", encoding="utf-8",
              newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Artist", "Title", "Album", "Spotify URL", "URI", "match_status"])
        w.writerows(csv_rows)
    return {"tracks": len(seen), "lines": len(lines)}
