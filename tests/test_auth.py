"""Callback-path handling. The bug this guards against: a one-shot server that
spends itself on Chrome's /favicon.ico request and never sees the real code."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tg2spotify.auth import parse_callback


def test_real_callback_is_recognised():
    ok, code, err = parse_callback("/callback?code=AQD123&state=xyz")
    assert ok and code == "AQD123" and err is None

def test_favicon_request_is_ignored():
    ok, code, err = parse_callback("/favicon.ico")
    assert (ok, code, err) == (False, None, None)

def test_bare_root_probe_is_ignored():
    # exactly what a port probe or a preconnect looks like
    assert parse_callback("/")[0] is False

def test_denied_authorisation_is_surfaced():
    ok, code, err = parse_callback("/callback?error=access_denied")
    assert ok and code is None and err == "access_denied"

def test_trailing_slash_still_matches():
    assert parse_callback("/callback/?code=X")[1] == "X"
