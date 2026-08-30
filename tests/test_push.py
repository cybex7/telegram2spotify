"""Push must be idempotent: re-running after an interruption has to top up the
same playlist, never create a second one."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tg2spotify import db, push


class FakeApi:
    """Records what was asked of it, so the test can assert on the calls."""
    def __init__(self, existing=None, pid="pl1"):
        self.created = []
        self.added = []
        self.removed = []
        self.store = {pid: list(existing or [])}

    def me(self):
        return {"id": "arash"}

    def create_playlist(self, user_id, name, public=True, description=""):
        pid = f"pl{len(self.store) if self.store else 1}"
        pid = "pl1" if "pl1" not in self.store else f"pl{len(self.store)+1}"
        self.store[pid] = []
        self.created.append((pid, name, public))
        return {"id": pid, "external_urls": {"spotify": f"https://open.spotify.com/playlist/{pid}"}}

    def playlist(self, pid):
        if pid not in self.store:
            raise KeyError(pid)
        return {"id": pid, "external_urls": {"spotify": f"https://open.spotify.com/playlist/{pid}"}}

    def playlist_uris(self, pid):
        return list(self.store.get(pid, []))

    def add_items(self, pid, uris):
        self.store[pid].extend(uris)
        self.added.append(list(uris))
        return {}

    def remove_items(self, pid, uris):
        self.removed.append(list(uris))
        self.store[pid] = [u for u in self.store[pid] if u not in set(uris)]
        return {}


def _db(tmp, rows):
    con = db.connect(tmp)
    for mid, uri, status in rows:
        con.execute("INSERT OR REPLACE INTO tracks (msg_id,status,spotify_uri) VALUES (?,?,?)",
                    (mid, status, uri))
    con.commit()
    return con


def test_first_run_creates_the_playlist(tmp="/tmp/tg2s_push_a.sqlite"):
    if os.path.exists(tmp): os.remove(tmp)
    con = _db(tmp, [(1, "spotify:track:a", "matched"), (2, "spotify:track:b", "matched")])
    api = FakeApi()
    res = push.run(con, api, "Music on 🎧")
    assert len(api.created) == 1
    assert res["added"] == 2

def test_rerun_tops_up_the_same_playlist(tmp="/tmp/tg2s_push_b.sqlite"):
    if os.path.exists(tmp): os.remove(tmp)
    con = _db(tmp, [(1, "spotify:track:a", "matched")])
    api = FakeApi()
    push.run(con, api, "Music on 🎧")
    # a later match arrives, then the push is run again
    con.execute("INSERT INTO tracks (msg_id,status,spotify_uri) VALUES (2,'matched','spotify:track:b')")
    con.commit()
    res = push.run(con, api, "Music on 🎧")
    assert len(api.created) == 1, "a second playlist was created"
    assert res["added"] == 1, "should add only the new track"
    assert res["already_present"] == 1

def test_duplicate_uris_are_added_once(tmp="/tmp/tg2s_push_c.sqlite"):
    if os.path.exists(tmp): os.remove(tmp)
    con = _db(tmp, [(1, "spotify:track:a", "matched"), (2, "spotify:track:a", "matched"),
                    (3, "spotify:track:b", "matched")])
    api = FakeApi()
    res = push.run(con, api, "Music on 🎧")
    assert res["added"] == 2 and res["unique"] == 2

def test_review_rows_only_included_when_asked(tmp="/tmp/tg2s_push_d.sqlite"):
    if os.path.exists(tmp): os.remove(tmp)
    con = _db(tmp, [(1, "spotify:track:a", "matched"), (2, "spotify:track:b", "review")])
    api = FakeApi()
    assert push.run(con, api, "P", include_review=False)["added"] == 1
    con2 = _db("/tmp/tg2s_push_e.sqlite", [(1, "spotify:track:a", "matched"),
                                           (2, "spotify:track:b", "review")])
    api2 = FakeApi()
    assert push.run(con2, api2, "P", include_review=True)["added"] == 2


def test_orphans_are_reported_but_kept_by_default(tmp="/tmp/tg2s_push_orphan.sqlite"):
    """A re-match can move a track to a better URI, leaving the old one behind.

    It is a real wrong song in the playlist, so it must be counted -- but not
    deleted unasked: the user was told to add the not-found pile by hand, and
    those additions are indistinguishable from orphans.
    """
    if os.path.exists(tmp): os.remove(tmp)
    con = _db(tmp, [(1, "spotify:track:new", "matched")])
    PID = "abcXYZ0123456789abcJKL"
    api = FakeApi(existing=["spotify:track:stale", "spotify:track:by_hand"], pid=PID)
    res = push.run(con, api, "Music on 🎧", existing_playlist=PID)
    assert res["orphans"] == 2, res
    assert res["pruned"] == 0, res
    assert api.removed == [], api.removed
    assert "spotify:track:by_hand" in api.playlist_uris(PID)


def test_prune_removes_orphans_when_asked(tmp="/tmp/tg2s_push_prune.sqlite"):
    if os.path.exists(tmp): os.remove(tmp)
    con = _db(tmp, [(1, "spotify:track:new", "matched")])
    PID = "abcXYZ0123456789abcJKL"
    api = FakeApi(existing=["spotify:track:stale"], pid=PID)
    res = push.run(con, api, "Music on 🎧", existing_playlist=PID, prune=True)
    assert res["pruned"] == 1, res
    assert api.playlist_uris(PID) == ["spotify:track:new"], api.playlist_uris(PID)
