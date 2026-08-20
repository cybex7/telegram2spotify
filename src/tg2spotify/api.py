"""Thin Spotify Web API client: urllib, rate-limit aware, resumable."""

import http.client
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

BASE = "https://api.spotify.com/v1"
# Spotify answered one 429 with Retry-After: 54879 (15.2 hours). Sleeping on
# that inside a request is indistinguishable from a hang, so anything beyond
# this is reported to the caller instead.
MAX_RETRY_AFTER_S = 300
# Development-mode quota is modest; pacing requests avoids earning a ban that
# costs far more time than the pacing does.
MIN_REQUEST_INTERVAL_S = 0.5


class Spotify:
    def __init__(self, auth, max_retries: int = 5,
                 min_interval: float = MIN_REQUEST_INTERVAL_S):
        self.auth = auth
        self.max_retries = max_retries
        self.min_interval = min_interval
        self.calls = 0
        self._last_call = 0.0

    # seams so tests can drive the retry logic without real sleeps or sockets
    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def _open(self, req, timeout: int = 30):
        return urllib.request.urlopen(req, timeout=timeout)

    def _pace(self) -> None:
        gap = time.time() - self._last_call
        if self.min_interval and gap < self.min_interval:
            self._sleep(self.min_interval - gap)
        self._last_call = time.time()

    def _request(self, method: str, path: str, body: Optional[dict] = None,
                 params: Optional[dict] = None) -> Any:
        url = BASE + path + (("?" + urllib.parse.urlencode(params)) if params else "")
        payload = json.dumps(body).encode() if body is not None else None

        for attempt in range(self.max_retries):
            req = urllib.request.Request(url, data=payload, method=method)
            req.add_header("Authorization", "Bearer " + self.auth.token())
            if payload:
                req.add_header("Content-Type", "application/json")
            self._pace()
            try:
                with self._open(req, timeout=30) as resp:
                    self.calls += 1
                    raw = resp.read()
                    return json.loads(raw.decode()) if raw else {}
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    wait = int(exc.headers.get("Retry-After", "2")) + 1
                    if wait > MAX_RETRY_AFTER_S:
                        hours = wait / 3600.0
                        raise RuntimeError(
                            f"Spotify rate limit: it asked us to wait {wait}s "
                            f"({hours:.1f} hours) before the next request. Not "
                            f"sleeping on that. Progress is saved -- re-run once "
                            f"the window clears."
                        ) from exc
                    print(f"  rate limited, sleeping {wait}s")
                    self._sleep(wait)
                    continue
                if exc.code == 401 and attempt == 0:
                    self.auth._tok.pop("access_token", None)   # force a refresh
                    continue
                if exc.code >= 500:
                    self._sleep(2 ** attempt)
                    continue
                raise
            except urllib.error.URLError:
                self._sleep(2 ** attempt)
            except (http.client.IncompleteRead, http.client.RemoteDisconnected,
                    ConnectionError, socket.timeout) as exc:
                # Seen once in 50 searches, so certain to recur over thousands.
                # Without this the hypothesis was silently skipped, quietly
                # costing the track its best chance of a match.
                if attempt == self.max_retries - 1:
                    raise
                self._sleep(2 ** attempt)
        raise RuntimeError(f"giving up on {method} {path}")

    # ---- endpoints actually used

    def me(self) -> dict:
        return self._request("GET", "/me")

    def search_tracks(self, query: str, limit: int = 5) -> List[dict]:
        res = self._request("GET", "/search",
                            params={"q": query, "type": "track", "limit": limit})
        return (res.get("tracks") or {}).get("items") or []

    def create_playlist(self, user_id: str, name: str, public: bool = True,
                        description: str = "") -> dict:
        return self._request("POST", f"/users/{user_id}/playlists",
                             body={"name": name, "public": public,
                                   "description": description})

    def playlist(self, playlist_id: str) -> dict:
        return self._request("GET", f"/playlists/{playlist_id}",
                             params={"fields": "id,name,external_urls"})

    def add_items(self, playlist_id: str, uris: List[str]) -> dict:
        return self._request("POST", f"/playlists/{playlist_id}/tracks",
                             body={"uris": uris})

    def playlist_uris(self, playlist_id: str) -> List[str]:
        """Existing track URIs, so a re-run never double-adds."""
        out, offset = [], 0
        while True:
            page = self._request("GET", f"/playlists/{playlist_id}/tracks",
                                 params={"limit": 100, "offset": offset,
                                         "fields": "items(track(uri)),total"})
            items = page.get("items") or []
            out.extend((i.get("track") or {}).get("uri") for i in items if i.get("track"))
            offset += len(items)
            if not items or offset >= page.get("total", 0):
                return [u for u in out if u]
