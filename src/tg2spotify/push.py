"""Stage 6 — fill a playlist with matched tracks, 100 per request.

Creating a playlist returns 403 on this app, so an existing playlist can be
supplied instead: the user makes an empty one in Spotify and passes its link.
"""

import re
from typing import Dict, List, Optional

BATCH = 100

_PLAYLIST_REF = re.compile(
    r"(?:^|playlist[:/])([A-Za-z0-9]{16,})(?:\?|$)")


def playlist_id_from(ref: Optional[str]) -> str:
    """Extract a playlist id from a URL, a spotify: URI, or a bare id."""
    if not ref or not isinstance(ref, str):
        raise ValueError("no playlist reference given")
    if "track" in ref or "album" in ref:
        raise ValueError(f"not a playlist reference: {ref}")
    m = _PLAYLIST_REF.search(ref.strip())
    if not m:
        raise ValueError(f"could not find a playlist id in {ref!r}")
    return m.group(1)


def run(con, api, playlist_name: str, public: bool = True,
        include_review: bool = False,
        existing_playlist: Optional[str] = None) -> Dict[str, object]:
    states = ["matched"] + (["review"] if include_review else [])
    rows = con.execute(
        "SELECT msg_id, spotify_uri FROM tracks WHERE status IN (%s) AND spotify_uri IS NOT NULL"
        % ",".join("?" * len(states)), states).fetchall()

    # de-duplicate by URI: the corpus has 12 duplicate performer+title pairs
    uris: List[str] = []
    for r in rows:
        if r["spotify_uri"] not in uris:
            uris.append(r["spotify_uri"])

    # Reuse the playlist from a previous run: an interrupted push must top the
    # same one up, never leave a half-filled duplicate behind.
    if existing_playlist:
        con.execute("INSERT OR REPLACE INTO meta VALUES ('playlist_id', ?)",
                    (playlist_id_from(existing_playlist),))
        con.commit()

    stored = con.execute("SELECT value FROM meta WHERE key='playlist_id'").fetchone()
    playlist = None
    if stored:
        try:
            playlist = api.playlist(stored["value"])
        except Exception:
            playlist = None            # deleted upstream: fall through and recreate

    if playlist is None:
        me = api.me()
        playlist = api.create_playlist(
            me["id"], playlist_name, public=public,
            description="Imported from my Telegram channel archive (2018-2026).")
        con.execute("INSERT OR REPLACE INTO meta VALUES ('playlist_id', ?)",
                    (playlist["id"],))
        con.commit()

    existing = set(api.playlist_uris(playlist["id"]))
    fresh = [u for u in uris if u not in existing]

    added = 0
    for i in range(0, len(fresh), BATCH):
        chunk = fresh[i:i + BATCH]
        api.add_items(playlist["id"], chunk)
        added += len(chunk)
        print(f"  added {added}/{len(fresh)}")

    return {"playlist_url": playlist["external_urls"]["spotify"],
            "playlist_id": playlist["id"],
            "candidates": len(rows), "unique": len(uris),
            "already_present": len(uris) - len(fresh), "added": added}
