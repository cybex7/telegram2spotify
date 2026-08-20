"""A dead network must abort the run, not quietly mark every track as missing.

Without this guard a proxy outage looks exactly like a successful run whose
tracks happen not to exist on Spotify -- the worst kind of failure, because the
output is plausible.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tg2spotify import db, match


class DeadNetworkApi:
    calls = 0
    def search_tracks(self, query, limit=5):
        DeadNetworkApi.calls += 1
        raise OSError("[Errno 101] Network is unreachable")


class WorkingApi:
    def search_tracks(self, query, limit=5):
        return [{"name": "Hamdam", "uri": "spotify:track:x", "duration_ms": 250000,
                 "artists": [{"name": "Ebi"}]}]


def _seed(path, n):
    if os.path.exists(path):
        os.remove(path)
    con = db.connect(path)
    for i in range(1, n + 1):
        con.execute("""INSERT INTO tracks (msg_id,status,duration_tg,clean_artist,clean_title)
                       VALUES (?,'ingested',250,'Ebi','Hamdam')""", (i,))
        con.execute("INSERT INTO hypotheses VALUES (?,0,'Ebi','Hamdam','performer+title',0.9,0)",
                    (i,))
    con.commit()
    return con


def test_persistent_network_failure_aborts():
    con = _seed("/tmp/tg2s_guard_a.sqlite", 40)
    try:
        match.run(con, DeadNetworkApi(), verbose=False)
    except RuntimeError as exc:
        assert "network" in str(exc).lower(), exc
    else:
        raise AssertionError("a dead network was accepted as 'no matches found'")
    unresolved = con.execute(
        "SELECT COUNT(*) FROM tracks WHERE status='ingested'").fetchone()[0]
    assert unresolved > 0, "aborted too late -- it processed everything anyway"

def test_healthy_network_is_unaffected():
    con = _seed("/tmp/tg2s_guard_b.sqlite", 15)
    stats = match.run(con, WorkingApi(), verbose=False)
    assert stats["auto"] == 15, stats
