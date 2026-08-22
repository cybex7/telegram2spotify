#!/usr/bin/env python3
"""Stage 3: match every track against Spotify.

    python3 run_match.py             # every not-yet-tried track
    python3 run_match.py 20          # dry-ish run over the first 20 only
    python3 run_match.py --retry-hard  # also re-try previous review/miss tracks

Search quota is the bottleneck: re-trying review/miss costs ~7 searches each
for roughly one conversion in fifty, so it is opt-in.
"""
import os, socket, sys
socket.setdefaulttimeout(45)   # a dead proxy must fail fast, not hang
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))
from tg2spotify import db, match
from tg2spotify.api import RateLimited, Spotify
from tg2spotify.auth import Auth

from tg2spotify.config import client_id

flags = [a for a in sys.argv[1:] if a.startswith("--")]
nums = [a for a in sys.argv[1:] if not a.startswith("--")]
limit = int(nums[0]) if nums else None
retry_hard = "--retry-hard" in flags
con = db.connect(os.path.join(ROOT, "state.sqlite"))
api = Spotify(Auth(client_id(), os.path.join(ROOT, ".spotify_token.json")))
print("authorised as:", api.me().get("display_name"), "\n")

# A rate-limit abort mid-run is normal, not exceptional. Report on what was
# matched anyway: twice now the reports have sat stale for a day because the
# abort skipped write_reports, and stale reports read as fresh ones.
banned = None
try:
    stats = match.run(con, api, limit=limit, retry_hard=retry_hard)
except RateLimited as exc:
    banned = exc
    stats = {}
counts = match.write_reports(con, os.path.join(ROOT, "reports"))
print("\n--- stage 3 ---")
for k, v in {**stats, **counts}.items():
    print(f"{k:12} {v}")
print(f"\nAPI calls: {api.calls}")
if banned is not None:
    print("\nSTOPPED EARLY -- %s" % banned)
    print("Reports above are up to date. Pushing to the playlist still works:")
    print("  the ban is on /search only. Re-run this once the window clears.")
    sys.exit(2)
