#!/usr/bin/env python3
"""Stage 3: match every track against Spotify.

    python3 run_match.py            # all tracks
    python3 run_match.py 20         # dry-ish run over the first 20 only
"""
import os, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))
from tg2spotify import db, match
from tg2spotify.api import Spotify
from tg2spotify.auth import Auth

CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "c5f9bf69f8b346c3a9a0df84392eb807")

limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
con = db.connect(os.path.join(ROOT, "state.sqlite"))
api = Spotify(Auth(CLIENT_ID, os.path.join(ROOT, ".spotify_token.json")))
print("authorised as:", api.me().get("display_name"), "\n")

stats = match.run(con, api, limit=limit)
counts = match.write_reports(con, os.path.join(ROOT, "reports"))
print("\n--- stage 3 ---")
for k, v in {**stats, **counts}.items():
    print(f"{k:12} {v}")
print(f"\nAPI calls: {api.calls}")
