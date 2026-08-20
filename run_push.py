#!/usr/bin/env python3
"""Stage 6: create the playlist and push matched tracks.

    python3 run_push.py "Music on 🎧"
    python3 run_push.py "Music on 🎧" --include-review
"""
import os, socket, sys
socket.setdefaulttimeout(45)   # a dead proxy must fail fast, not hang
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))
from tg2spotify import db, push
from tg2spotify.api import Spotify
from tg2spotify.auth import Auth

CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "c5f9bf69f8b346c3a9a0df84392eb807")
name = sys.argv[1] if len(sys.argv) > 1 else "Music on 🎧"
include_review = "--include-review" in sys.argv

con = db.connect(os.path.join(ROOT, "state.sqlite"))
api = Spotify(Auth(CLIENT_ID, os.path.join(ROOT, ".spotify_token.json")))
result = push.run(con, api, name, public=True, include_review=include_review)
for k, v in result.items():
    print(f"{k:14} {v}")
