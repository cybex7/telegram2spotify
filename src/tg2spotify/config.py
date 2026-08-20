"""Local configuration, kept out of the repository.

The client id is a public identifier, but it is *yours*: anyone running with it
spends your app's search quota and inherits your rate-limit bans. So it lives in
an environment variable or a gitignored file, never in the source.
"""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLIENT_ID_FILE = os.path.join(ROOT, ".client_id")
EXPORT_FILE = os.path.join(ROOT, ".export_path")

SETUP = """
Spotify client id not configured.

  1. Create a free app at https://developer.spotify.com/dashboard
  2. Set its Redirect URI to exactly:  http://127.0.0.1:8888/callback
  3. Tick "Web API", save, and copy the Client ID
  4. Then either:
       echo YOUR_CLIENT_ID > .client_id
     or:
       export SPOTIFY_CLIENT_ID=YOUR_CLIENT_ID

No client secret is needed -- this uses PKCE.
"""


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip() or None
    except OSError:
        return None


def client_id() -> str:
    value = os.environ.get("SPOTIFY_CLIENT_ID") or _read(CLIENT_ID_FILE)
    if not value:
        raise SystemExit(SETUP)
    return value


def export_dir() -> str:
    """Directory of the Telegram Desktop export (holds result.json and files/)."""
    value = os.environ.get("TELEGRAM_EXPORT") or _read(EXPORT_FILE)
    if not value:
        raise SystemExit(
            "\nTelegram export directory not configured. Export the channel from\n"
            "Telegram Desktop (machine-readable JSON), then:\n\n"
            "  echo '/path/to/ChatExport_YYYY-MM-DD' > .export_path\n"
            "or:\n"
            "  export TELEGRAM_EXPORT='/path/to/ChatExport_YYYY-MM-DD'\n")
    if not os.path.isfile(os.path.join(value, "result.json")):
        raise SystemExit(f"\nNo result.json inside {value!r} -- is that the export folder?\n")
    return value
