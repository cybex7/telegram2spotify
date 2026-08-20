"""Spotify OAuth via Authorization Code + PKCE. Stdlib only.

PKCE needs no client secret: the client id is a public identifier, and the
one-time consent happens in the user's own browser where they are already
logged in. Tokens are cached locally (gitignored) and refreshed silently.
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from typing import Optional

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = "playlist-modify-public playlist-modify-private playlist-read-private"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    code: Optional[str] = None
    error: Optional[str] = None

    def do_GET(self):  # noqa: N802
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _CallbackHandler.code = (params.get("code") or [None])[0]
        _CallbackHandler.error = (params.get("error") or [None])[0]
        body = ("Authorised. You can close this tab and return to the terminal."
                if _CallbackHandler.code else
                f"Authorisation failed: {_CallbackHandler.error}")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *_args):
        pass  # keep the terminal clean


def _post_form(data: dict) -> dict:
    req = urllib.request.Request(
        TOKEN_URL, data=urllib.parse.urlencode(data).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


class Auth:
    def __init__(self, client_id: str, cache_path: str):
        self.client_id = client_id
        self.cache_path = cache_path
        self._tok = self._load()

    def _load(self) -> dict:
        if os.path.isfile(self.cache_path):
            try:
                with open(self.cache_path, encoding="utf-8") as fh:
                    return json.load(fh)
            except (OSError, ValueError):
                pass
        return {}

    def _save(self) -> None:
        with open(self.cache_path, "w", encoding="utf-8") as fh:
            json.dump(self._tok, fh)
        os.chmod(self.cache_path, 0o600)

    def token(self) -> str:
        """A valid access token, doing the interactive dance only if needed."""
        if self._tok.get("access_token") and self._tok.get("expires_at", 0) > time.time() + 60:
            return self._tok["access_token"]
        if self._tok.get("refresh_token"):
            try:
                return self._refresh()
            except Exception:
                pass  # fall through to a fresh consent
        return self._authorise()

    def _store(self, payload: dict) -> str:
        self._tok["access_token"] = payload["access_token"]
        self._tok["expires_at"] = time.time() + int(payload.get("expires_in", 3600))
        if payload.get("refresh_token"):
            self._tok["refresh_token"] = payload["refresh_token"]
        self._save()
        return self._tok["access_token"]

    def _refresh(self) -> str:
        return self._store(_post_form({
            "grant_type": "refresh_token",
            "refresh_token": self._tok["refresh_token"],
            "client_id": self.client_id,
        }))

    def _authorise(self) -> str:
        verifier = _b64url(secrets.token_bytes(64))
        challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
        state = secrets.token_urlsafe(16)
        url = AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": self.client_id, "response_type": "code",
            "redirect_uri": REDIRECT_URI, "scope": SCOPES,
            "code_challenge_method": "S256", "code_challenge": challenge,
            "state": state,
        })

        server = http.server.HTTPServer(("127.0.0.1", 8888), _CallbackHandler)
        threading.Thread(target=server.handle_request, daemon=True).start()

        print("\nOpening Spotify for one consent click:\n  " + url + "\n")
        try:
            webbrowser.open(url)
        except Exception:
            print("(could not open a browser automatically -- paste the URL above)")

        deadline = time.time() + 300
        while _CallbackHandler.code is None and _CallbackHandler.error is None:
            if time.time() > deadline:
                raise TimeoutError("no callback within 5 minutes")
            time.sleep(0.3)
        server.server_close()
        if _CallbackHandler.error:
            raise RuntimeError("authorisation denied: " + _CallbackHandler.error)

        return self._store(_post_form({
            "grant_type": "authorization_code",
            "code": _CallbackHandler.code,
            "redirect_uri": REDIRECT_URI,
            "client_id": self.client_id,
            "code_verifier": verifier,
        }))
