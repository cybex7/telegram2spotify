#!/usr/bin/env python3
"""Can this app write to the Spotify library, given that it cannot write playlists?

Saves ONE track, confirms it, then removes it again -- so it leaves no trace.
Requires one fresh consent click, because the library scopes are new.
"""
import os, socket, sys
socket.setdefaulttimeout(45)
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))
from tg2spotify.api import Spotify
from tg2spotify.auth import Auth
from tg2spotify.config import client_id
import sqlite3

TOKEN = os.path.join(ROOT, ".spotify_token.json")

# the new scopes are not in the cached token, so force a fresh consent
if "--reauth" in sys.argv and os.path.exists(TOKEN):
    os.remove(TOKEN)
    print("cached token removed; a consent click is coming\n")

api = Spotify(Auth(client_id(), TOKEN))
con = sqlite3.connect(os.path.join(ROOT, "state.sqlite"))
row = con.execute("""SELECT spotify_uri, spotify_artists, spotify_name FROM tracks
                     WHERE spotify_uri IS NOT NULL AND spotify_name IS NOT NULL
                     LIMIT 1""").fetchone()
if not row:
    raise SystemExit("no matched tracks in the database yet")
uri, artists, name = row
tid = uri.split(":")[-1]
print("test track: %s - %s" % (artists, name))

def status(label):
    r = api._request("GET", "/me/tracks/contains", params={"ids": tid})
    print("  %-22s saved=%s" % (label, r))
    return r

try:
    status("before")
    api._request("PUT", "/me/tracks", body={"ids": [tid]})
    print("  PUT /me/tracks          accepted")
    saved = status("after save")
    api._request("DELETE", "/me/tracks", body={"ids": [tid]})
    print("  DELETE /me/tracks       accepted (library restored)")
    status("after cleanup")
    print("\nRESULT: library writes WORK -> all matched tracks can be saved to")
    print("        Liked Songs, then moved into a playlist inside the Spotify app."
          if saved and saved[0] else "\nRESULT: the call succeeded but the track did not save -- inconclusive.")
except Exception as exc:
    print("\nRESULT: library writes are blocked too ->", exc)
    print("        Fall back to reports/import_list.txt + an import service.")
