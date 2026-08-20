#!/usr/bin/env python3
"""Fetch Spotify's canonical names and write the import files."""
import os, socket, sys
socket.setdefaulttimeout(45)
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))
from tg2spotify import db, export
from tg2spotify.api import Spotify
from tg2spotify.auth import Auth

con = db.connect(os.path.join(ROOT, "state.sqlite"))
api = Spotify(Auth(os.environ.get("SPOTIFY_CLIENT_ID", "c5f9bf69f8b346c3a9a0df84392eb807"),
                   os.path.join(ROOT, ".spotify_token.json")))
print(export.fetch_canonical(con, api))
print(export.write_import_files(con, os.path.join(ROOT, "reports")))
