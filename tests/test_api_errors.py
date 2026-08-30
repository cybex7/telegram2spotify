"""Every Spotify error we predicted must come back as a message a human can
act on without asking an AI what it means -- not a bare status code or a raw
traceback. One test per predicted failure mode."""
import io, json, os, sys, urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tg2spotify.api import Spotify


class FakeAuth:
    _tok = {}
    def token(self):
        return "t"


def _http_error(code, body=None, headers=None):
    fp = io.BytesIO(json.dumps(body).encode()) if body is not None else io.BytesIO(b"")
    return urllib.error.HTTPError(
        "https://api.spotify.com/v1/x", code, "err", headers or {}, fp)


def _api(no_sleep=True):
    api = Spotify(FakeAuth(), min_interval=0)
    if no_sleep:
        api._sleep = lambda _s: None
    return api


def test_persistent_401_after_refresh_blames_the_refresh_token():
    api = _api()
    def opener(*_a, **_k):
        raise _http_error(401)
    api._open = opener
    try:
        api._request("GET", "/me")
        raise AssertionError("persistent 401 was accepted")
    except RuntimeError as exc:
        msg = str(exc).lower()
        assert "401" in str(exc)
        assert "refresh" in msg and ".spotify_token.json" in str(exc), exc


def test_403_insufficient_scope_names_the_fix():
    api = _api()
    def opener(*_a, **_k):
        raise _http_error(403, {"error": {"status": 403,
                                          "message": "Insufficient client scope"}})
    api._open = opener
    try:
        api._request("GET", "/me/tracks")
        raise AssertionError("403 was accepted")
    except RuntimeError as exc:
        assert "scope" in str(exc).lower(), exc


def test_403_on_retired_tracks_subresource_points_at_items():
    api = _api()
    def opener(*_a, **_k):
        raise _http_error(403, {"error": {"status": 403, "message": "Forbidden"}})
    api._open = opener
    try:
        api._request("POST", "/playlists/abc/tracks")
        raise AssertionError("403 was accepted")
    except RuntimeError as exc:
        assert "/items" in str(exc), exc


def test_404_hints_wrong_or_deleted_id():
    api = _api()
    def opener(*_a, **_k):
        raise _http_error(404, {"error": {"status": 404, "message": "Not found"}})
    api._open = opener
    try:
        api._request("GET", "/playlists/doesnotexist")
        raise AssertionError("404 was accepted")
    except RuntimeError as exc:
        assert "wrong" in str(exc).lower() or "deleted" in str(exc).lower(), exc


def test_400_points_at_a_bug_not_the_users_setup():
    api = _api()
    def opener(*_a, **_k):
        raise _http_error(400, {"error": {"status": 400, "message": "bad request"}})
    api._open = opener
    try:
        api._request("GET", "/search")
        raise AssertionError("400 was accepted")
    except RuntimeError as exc:
        assert "issue" in str(exc).lower() or "bug" in str(exc).lower(), exc


def test_5xx_exhausted_blames_spotify_not_the_user():
    api = _api()
    def opener(*_a, **_k):
        raise _http_error(503)
    api._open = opener
    try:
        api._request("GET", "/search")
        raise AssertionError("exhausted 503s were accepted")
    except RuntimeError as exc:
        assert "spotify" in str(exc).lower(), exc


def test_malformed_json_response_is_reported_clearly():
    api = _api()
    class _Resp:
        def read(self):
            return b"<html>not json</html>"
        def __enter__(self):
            return self
        def __exit__(self, *_a):
            return False
    api._open = lambda *_a, **_k: _Resp()
    try:
        api._request("GET", "/search")
        raise AssertionError("malformed JSON was accepted")
    except RuntimeError as exc:
        assert "json" in str(exc).lower(), exc


def test_network_down_exhausted_suggests_checking_the_connection():
    api = _api()
    def opener(*_a, **_k):
        raise urllib.error.URLError("nope")
    api._open = opener
    try:
        api._request("GET", "/search")
        raise AssertionError("exhausted network errors were accepted")
    except RuntimeError as exc:
        assert "internet connection" in str(exc).lower(), exc
