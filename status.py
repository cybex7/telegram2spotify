#!/usr/bin/env python3
"""One command, one screen: everything a new session needs to resume.

Deliberately compact -- reading this output should replace re-exploring the
repo, the database and the reports.
"""
import os
import sqlite3

ROOT = os.path.dirname(os.path.abspath(__file__))
con = sqlite3.connect(os.path.join(ROOT, "state.sqlite"))


def q(sql):
    return con.execute(sql).fetchone()[0]


COUNT = "SELECT COUNT(*) FROM tracks WHERE status=?"
todo = con.execute(COUNT, ("ingested",)).fetchone()[0]

print("tracks           %d   (corpus: 738 audio messages)" % q("SELECT COUNT(*) FROM tracks"))
print("  matched        %d" % con.execute(COUNT, ("matched",)).fetchone()[0])
print("  review         %d  (published too, per the user's choice)"
      % con.execute(COUNT, ("review",)).fetchone()[0])
print("  miss           %d" % con.execute(COUNT, ("miss",)).fetchone()[0])
print("  NOT YET DONE   %d" % todo)
print("unique uris      %d"
      % q("SELECT COUNT(DISTINCT spotify_uri) FROM tracks WHERE spotify_uri IS NOT NULL"))
print("canonical names  %d"
      % q("SELECT COUNT(*) FROM tracks WHERE spotify_name IS NOT NULL AND spotify_name <> ''"))

pl = con.execute("SELECT value FROM meta WHERE key='playlist_id'").fetchone()
print("playlist id      %s" % (pl[0] if pl else "(none stored)"))

rep = os.path.join(ROOT, "reports")
if os.path.isdir(rep):
    print("\nreports/")
    for f in sorted(os.listdir(rep)):
        p = os.path.join(rep, f)
        if f.endswith((".csv", ".txt")):
            with open(p, encoding="utf-8", errors="replace") as fh:
                n = sum(1 for _ in fh)
            print("  %-22s %d lines" % (f, n))

print("\nnext step:")
if todo:
    print("  python3 run_match.py     # %d left; aborts at once if the quota is still spent" % todo)
pid = pl[0] if pl else "<playlist-id>"
print('  python3 run_push.py "Music On" "%s" --include-review   # idempotent' % pid)
print("  python3 run_export.py    # refresh import_list.txt / .csv (fallback record)")
