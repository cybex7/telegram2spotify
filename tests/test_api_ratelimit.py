"""A huge Retry-After must abort with a clear message, not block for hours.

The run that appeared to hang for 8 hours was sleeping on a Retry-After of
54879s (15.2h) inside a single request.
"""
import os, sys, urllib.error
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tg2spotify.api import Spotify, MAX_RETRY_AFTER_S


class FakeAuth:
    _tok = {}
    def token(self):
        return "t"


def _http_error(retry_after):
    return urllib.error.HTTPError(
        "https://api.spotify.com/v1/search", 429, "Too Many Requests",
        {"Retry-After": str(retry_after)}, None)


def test_long_retry_after_aborts_instead_of_sleeping():
    api = Spotify(FakeAuth())
    slept = []
    api._sleep = slept.append
    def opener(*_a, **_k):
        raise _http_error(54879)
    api._open = opener
    try:
        api.search_tracks("anything")
    except RuntimeError as exc:
        assert "rate limit" in str(exc).lower(), exc
        assert "54879" in str(exc) or "15" in str(exc), exc
    else:
        raise AssertionError("a 15-hour Retry-After was accepted")
    assert not slept, f"it slept anyway: {slept}"


def test_short_retry_after_is_honoured():
    api = Spotify(FakeAuth())
    slept = []
    api._sleep = slept.append
    state = {"n": 0}
    def opener(*_a, **_k):
        state["n"] += 1
        if state["n"] == 1:
            raise _http_error(2)
        class R:
            def read(self): return b'{"tracks":{"items":[]}}'
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return R()
    api._open = opener
    assert api.search_tracks("anything") == []
    assert slept and slept[0] <= MAX_RETRY_AFTER_S
