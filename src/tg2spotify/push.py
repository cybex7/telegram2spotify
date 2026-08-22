"""Stage 6 — fill a playlist with matched tracks, 100 per request.

An existing playlist can be supplied instead of creating one: pass its link and
an interrupted run tops up the same playlist rather than leaving duplicates.

Writes go to POST /playlists/{id}/items. The retired /tracks sub-resource
answers a bare 403 "Forbidden" that looks exactly like an app-level ban -- see
tests/test_playlist_items_path.py.
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
        existing_playlist: Optional[str] = None,
        prune: bool = False) -> Dict[str, object]:
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

    # A re-match can move a track to a better URI, orphaning the one already
    # pushed -- a wrong song that no longer corresponds to any row. Pruning is
    # opt-in because it also removes anything the user added to the playlist by
    # hand, which is exactly what they were told to do for the not-found pile.
    orphans = sorted(existing - set(uris))
    pruned = 0
    if prune and orphans:
        for i in range(0, len(orphans), BATCH):
            api.remove_items(playlist["id"], orphans[i:i + BATCH])
            pruned += len(orphans[i:i + BATCH])

    added = 0
    for i in range(0, len(fresh), BATCH):
        chunk = fresh[i:i + BATCH]
        api.add_items(playlist["id"], chunk)
        added += len(chunk)
        print(f"  added {added}/{len(fresh)}")

    return {"playlist_url": playlist["external_urls"]["spotify"],
            "playlist_id": playlist["id"],
            "candidates": len(rows), "unique": len(uris),
            "already_present": len(uris) - len(fresh), "added": added,
            "orphans": len(orphans), "pruned": pruned}
