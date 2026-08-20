"""Stage 6 — create the playlist and add matched tracks, 100 per request."""

from typing import Dict, List

BATCH = 100


def run(con, api, playlist_name: str, public: bool = True,
        include_review: bool = False) -> Dict[str, object]:
    states = ["matched"] + (["review"] if include_review else [])
    rows = con.execute(
        "SELECT msg_id, spotify_uri FROM tracks WHERE status IN (%s) AND spotify_uri IS NOT NULL"
        % ",".join("?" * len(states)), states).fetchall()

    # de-duplicate by URI: the corpus has 12 duplicate performer+title pairs
    uris: List[str] = []
    for r in rows:
        if r["spotify_uri"] not in uris:
            uris.append(r["spotify_uri"])

    me = api.me()
    playlist = api.create_playlist(
        me["id"], playlist_name, public=public,
        description="Imported from my Telegram channel archive (2018-2026).")
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
            "candidates": len(rows), "unique": len(uris), "added": added}
