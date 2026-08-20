"""A rate-limit must stop the run instantly, not be retried per hypothesis.

The first attempt hammered the banned endpoint nine times for a single track
before moving on, which risks extending the ban.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from tg2spotify import db, match
from tg2spotify.api import RateLimited


class RateLimitedApi:
    def __init__(self):
        self.calls = 0
    def search_tracks(self, query, limit=5):
        self.calls += 1
        raise RateLimited("Spotify rate limit: wait 50852s (14.1 hours)")


def _seed(path, n):
    if os.path.exists(path):
        os.remove(path)
    con = db.connect(path)
    for i in range(1, n + 1):
        con.execute("""INSERT INTO tracks (msg_id,status,duration_tg,clean_artist,clean_title)
                       VALUES (?,'ingested',250,'Ebi','Hamdam')""", (i,))
        for rank in range(4):                      # several hypotheses per track
            con.execute("INSERT INTO hypotheses VALUES (?,?,'Ebi','Hamdam','x',0.9,0)",
                        (i, rank))
    con.commit()
    return con


def test_rate_limit_aborts_on_the_first_hit():
    con = _seed("/tmp/tg2s_rl.sqlite", 30)
    api = RateLimitedApi()
    try:
        match.run(con, api, verbose=False)
    except RateLimited:
        pass
    else:
        raise AssertionError("the run continued through a rate limit")
    assert api.calls == 1, f"hammered the banned endpoint {api.calls} times"
    assert con.execute("SELECT COUNT(*) FROM tracks WHERE status='ingested'"
                       ).fetchone()[0] == 30, "wrote results despite being blocked"
