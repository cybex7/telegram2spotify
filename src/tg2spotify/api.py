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


class RateLimited(RuntimeError):
    """Quota exhausted for hours. Callers must stop, not retry: repeat calls
    against a banned endpoint can extend the ban."""


def _explain_http_error(code: int, method: str, path: str, detail: str) -> str:
    """A plain-language guess at what a 4xx that isn't 401/404/429/5xx means,
    so a human can fix it without needing to ask an AI what Spotify meant."""
    low = detail.lower()
    if code == 403:
        if "insufficient client scope" in low:
            return ("the token is missing a scope this call needs. Add it to "
                    "SCOPES in auth.py, delete .spotify_token.json, and run "
                    "again for a fresh consent.")
        if "/playlists/" in path and path.rstrip("/").endswith("/tracks"):
            return ("Spotify retired this sub-resource for newer apps -- use "
                    "/playlists/{id}/items instead (see add_items/playlist_uris "
                    "in this file).")
        return ("check that every scope this call needs is both in SCOPES "
                "(auth.py) and was actually granted -- delete "
                ".spotify_token.json and re-run to force a fresh consent "
                "screen, then check the scopes listed there.")
    if code == 404:
        return ("the id in this request may be wrong, deleted, or belongs to "
                "a different account than the one that authorised this token.")
    if code == 400:
        return ("the request itself was malformed -- most likely a bug in "
                "this codebase rather than something to fix in your setup. "
                "please open an issue with this exact message.")
    return "see the message above; https://developer.spotify.com/documentation/web-api has the full error reference."


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
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise RuntimeError(
                    f"{method} {path} -> Spotify's response was not valid JSON. "
                    f"This is unusual; try again, and check "
                    f"https://developer.spotify.com/status if it keeps happening."
                ) from exc
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    wait = int(exc.headers.get("Retry-After", "2")) + 1
                    if wait > MAX_RETRY_AFTER_S:
                        hours = wait / 3600.0
                        raise RateLimited(
                            f"Spotify rate limit: it asked us to wait {wait}s "
                            f"({hours:.1f} hours) before the next request. Not "
                            f"sleeping on that. Progress is saved -- re-run once "
                            f"the window clears."
                        ) from exc
                    print(f"  rate limited, sleeping {wait}s")
                    self._sleep(wait)
                    continue
                if exc.code == 401:
                    if attempt == 0:
                        self.auth._tok.pop("access_token", None)   # force a refresh
                        continue
                    raise RuntimeError(
                        f"{method} {path} -> HTTP 401, still unauthorised after "
                        f"refreshing the token. The refresh token itself is "
                        f"probably invalid (you removed the app's access under "
                        f"Spotify account -> Apps, or a scope changed).\n"
                        f"  fix: delete .spotify_token.json and run again for a "
                        f"fresh consent."
                    ) from exc
                if exc.code >= 500:
                    if attempt < self.max_retries - 1:
                        self._sleep(2 ** attempt)
                        continue
                    raise RuntimeError(
                        f"{method} {path} -> HTTP {exc.code} from Spotify after "
                        f"{self.max_retries} attempts. This is on Spotify's side, "
                        f"not a bug here -- wait a few minutes and run again; "
                        f"progress is saved."
                    ) from exc
                # Spotify explains itself in the body; hiding it wastes a debug cycle.
                try:
                    detail = exc.read().decode(errors="replace")[:400]
                except Exception:
                    detail = "<no body>"
                raise RuntimeError(
                    f"{method} {path} -> HTTP {exc.code}: {detail}\n"
                    f"  hint: {_explain_http_error(exc.code, method, path, detail)}"
                ) from exc
            except urllib.error.URLError as exc:
                if attempt == self.max_retries - 1:
                    raise RuntimeError(
                        f"{method} {path} failed after {self.max_retries} "
                        f"attempts: {exc.reason}. Check your internet connection "
                        f"and run again; progress is saved."
                    ) from exc
                self._sleep(2 ** attempt)
            except (http.client.IncompleteRead, http.client.RemoteDisconnected,
                    ConnectionError, socket.timeout) as exc:
                # Seen once in 50 searches, so certain to recur over thousands.
                # Without this the hypothesis was silently skipped, quietly
                # costing the track its best chance of a match.
                if attempt == self.max_retries - 1:
                    raise RuntimeError(
                        f"{method} {path} failed after {self.max_retries} "
                        f"attempts: {type(exc).__name__}: {exc}. This usually "
                        f"clears on its own -- run again in a moment; progress "
                        f"is saved."
                    ) from exc
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
        return self._request("POST", "/me/playlists",
                             body={"name": name, "public": public,
                                   "description": description})

    def playlist(self, playlist_id: str) -> dict:
        return self._request("GET", f"/playlists/{playlist_id}",
                             params={"fields": "id,name,external_urls"})

    def add_items(self, playlist_id: str, uris: List[str]) -> dict:
        return self._request("POST", f"/playlists/{playlist_id}/items",
                             body={"uris": uris})

    def remove_items(self, playlist_id: str, uris: List[str]) -> dict:
        """Drop URIs from a playlist. The delete body keys on "items" too."""
        return self._request("DELETE", f"/playlists/{playlist_id}/items",
                             body={"items": [{"uri": u} for u in uris]})

    def playlist_uris(self, playlist_id: str) -> List[str]:
        """Existing track URIs, so a re-run never double-adds."""
        out, offset = [], 0
        while True:
            page = self._request("GET", f"/playlists/{playlist_id}/items",
                                 params={"limit": 100, "offset": offset,
                                         "fields": "items(item(uri)),total"})
            items = page.get("items") or []
            # /items names the payload "item"; the retired /tracks called it "track"
            for i in items:
                entry = i.get("item") or i.get("track") or {}
                out.append(entry.get("uri"))
            offset += len(items)
            if not items or offset >= page.get("total", 0):
                return [u for u in out if u]
