"""Playlist writes must go to /items, never the retired /tracks sub-resource.

Spotify answers `POST /playlists/{id}/tracks` with a bare 403 "Forbidden" for
apps created after the endpoint was retired, while `POST /playlists/{id}/items`
works with the very same token and scopes. That 403 is indistinguishable from an
app-level ban, and it cost a full day of chasing the wrong theory -- so the path
is pinned here.

The second trap: /items names the payload "item"; /tracks called it "track".
Reading uris with the old key silently returns nothing, which makes the
de-duplication pass believe an already-full playlist is empty.
"""
import io, json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tg2spotify.api import Spotify


class FakeAuth:
    _tok = {}
    def token(self):
        return "t"


class _Resp:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode()
    def read(self):
        return self._raw
    def __enter__(self):
        return self
    def __exit__(self, *_a):
        return False


def _recording_api(payload):
    """A Spotify client that records (method, url) instead of hitting the net."""
    api = Spotify(FakeAuth(), min_interval=0)
    seen = []
    def opener(req, timeout=30):
        seen.append((req.get_method(), req.full_url))
        return _Resp(payload)
    api._open = opener
    return api, seen


def test_add_items_posts_to_items_not_tracks():
    api, seen = _recording_api({"snapshot_id": "s"})
    api.add_items("PL", ["spotify:track:1"])
    method, url = seen[0]
    assert method == "POST", method
    assert url.endswith("/playlists/PL/items"), url
    assert "/tracks" not in url, f"retired sub-resource: {url}"


def test_playlist_uris_reads_the_item_key():
    payload = {"total": 1, "items": [{"item": {"uri": "spotify:track:abc"}}]}
    api, seen = _recording_api(payload)
    assert api.playlist_uris("PL") == ["spotify:track:abc"]
    assert "/playlists/PL/items" in seen[0][1], seen[0][1]


def test_playlist_uris_still_reads_a_legacy_track_key():
    """Fixtures and cached pages from the old endpoint must not break dedup."""
    payload = {"total": 1, "items": [{"track": {"uri": "spotify:track:old"}}]}
    api, _ = _recording_api(payload)
    assert api.playlist_uris("PL") == ["spotify:track:old"]


def test_create_playlist_uses_me_not_users():
    """POST /users/{id}/playlists is 403; POST /me/playlists is not."""
    api, seen = _recording_api({"id": "PL", "external_urls": {"spotify": "u"}})
    api.create_playlist("someuser", "name")
    method, url = seen[0]
    assert method == "POST", method
    assert url.endswith("/me/playlists"), url
    assert "/users/" not in url, f"restricted path: {url}"
