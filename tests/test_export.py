"""Import-list formatting. Feeds Soundiiz / TuneMyMusic, which do have write
access to Spotify -- the API write path is 403 for this app."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from tg2spotify.export import import_line, track_url


def test_line_is_artist_dash_title():
    assert import_line("The Beatles", "Let It Be - Remastered 2009") == \
        "The Beatles - Let It Be"

def test_remaster_suffix_removed_so_the_importer_matches():
    # importers match on plain names; a '- Remastered 2009' tail hurts
    assert import_line("Keane", "Somewhere Only We Know - Live") == \
        "Keane - Somewhere Only We Know"

def test_multiple_artists_use_the_first():
    assert import_line("King Raam, Eendo", "The Last Waltz") == \
        "King Raam - The Last Waltz"

def test_persian_names_survive():
    assert import_line("فرهاد مهراد", "آیینه ها") == "فرهاد مهراد - آیینه ها"

def test_internal_dash_in_title_is_kept():
    assert import_line("Artist", "Love - Hate") == "Artist - Love - Hate"

def test_url_from_uri():
    assert track_url("spotify:track:4u7Enebtm") == \
        "https://open.spotify.com/track/4u7Enebtm"
