"""Thin Spotify Web API client: urllib, rate-limit aware, resumable."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

BASE = "https://api.spotify.com/v1"


class Spotify:
    def __init__(self, auth, max_retries: int = 5):
        self.auth = auth
        self.max_retries = max_retries
        self.calls = 0

    def _request(self, method: str, path: str, body: Optional[dict] = None,
                 params: Optional[dict] = None) -> Any:
        url = BASE + path + (("?" + urllib.parse.urlencode(params)) if params else "")
        payload = json.dumps(body).encode() if body is not None else None

        for attempt in range(self.max_retries):
            req = urllib.request.Request(url, data=payload, method=method)
            req.add_header("Authorization", "Bearer " + self.auth.token())
            if payload:
                req.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    self.calls += 1
                    raw = resp.read()
                    return json.loads(raw.decode()) if raw else {}
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    wait = int(exc.headers.get("Retry-After", "2")) + 1
                    print(f"  rate limited, sleeping {wait}s")
                    time.sleep(wait)
                    continue
                if exc.code == 401 and attempt == 0:
                    self.auth._tok.pop("access_token", None)   # force a refresh
                    continue
                if exc.code >= 500:
                    time.sleep(2 ** attempt)
                    continue
                raise
            except urllib.error.URLError:
                time.sleep(2 ** attempt)
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
