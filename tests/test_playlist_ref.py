"""Accepting an existing playlist, so an interrupted push tops up the same one."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from tg2spotify.push import playlist_id_from

def test_open_spotify_url():
    assert playlist_id_from(
        "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M") == "37i9dQZF1DXcBWIGoYBM5M"

def test_url_with_query_and_locale():
    assert playlist_id_from(
        "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc123") == "37i9dQZF1DXcBWIGoYBM5M"

def test_spotify_uri():
    assert playlist_id_from("spotify:playlist:37i9dQZF1DXcBWIGoYBM5M") == "37i9dQZF1DXcBWIGoYBM5M"

def test_bare_id_passes_through():
    assert playlist_id_from("37i9dQZF1DXcBWIGoYBM5M") == "37i9dQZF1DXcBWIGoYBM5M"

def test_rejects_a_track_url():
    for bad in ("https://open.spotify.com/track/abc", "spotify:track:abc", "", None):
        try:
            playlist_id_from(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted a non-playlist reference: {bad!r}")
