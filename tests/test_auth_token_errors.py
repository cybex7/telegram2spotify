"""The token endpoint (accounts.spotify.com) had zero error handling: a wrong
client id or an expired auth code crashed with a raw traceback instead of
telling the user what to do. One test per predicted Spotify auth error."""
import io, json, os, sys, urllib.error, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tg2spotify import auth


def _fake_urlopen(code, error, description=""):
    body = json.dumps({"error": error, "error_description": description}).encode()
    def opener(*_a, **_k):
        raise urllib.error.HTTPError(
            "https://accounts.spotify.com/api/token", code, "err", {},
            io.BytesIO(body))
    return opener


def _expect_runtime_error(error, description, contains):
    original = urllib.request.urlopen
    urllib.request.urlopen = _fake_urlopen(400, error, description)
    try:
        auth._post_form({"grant_type": "authorization_code"})
        raise AssertionError(f"{error} was accepted")
    except RuntimeError as exc:
        assert contains in str(exc).lower(), exc
    finally:
        urllib.request.urlopen = original


def test_invalid_client_blames_the_client_id_file():
    _expect_runtime_error("invalid_client", "Invalid client", ".client_id")

def test_invalid_grant_says_just_run_it_again():
    _expect_runtime_error("invalid_grant", "expired code", "run the script again")

def test_invalid_request_points_at_redirect_uri():
    _expect_runtime_error("invalid_request", "redirect_uri mismatch", "redirect uri")
