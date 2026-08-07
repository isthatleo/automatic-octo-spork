"""One-command OAuth refresh-token helper for Spotify and Google Calendar --
both need a one-time manual "authorization-code flow" (see .env.example)
that's normally done by hand through the provider's own dashboard/OAuth
playground. This does the whole dance locally instead: opens your browser
to the real consent screen, catches the redirect on a temporary localhost
server, exchanges the code for tokens, and prints the refresh token to put
in .env.

Usage:
    python scripts/get_oauth_refresh_token.py spotify
    python scripts/get_oauth_refresh_token.py google_calendar

Reads CLIENT_ID/CLIENT_SECRET from the backend's .env (already set for
both per .env.example) -- only the refresh token itself is missing.

Spotify: the redirect URI below (http://127.0.0.1:8765/callback) must be
added under your app's "Redirect URIs" at
https://developer.spotify.com/dashboard first (Spotify rejects any
redirect URI that isn't pre-registered exactly) -- use the literal IP
127.0.0.1, not the hostname "localhost": Spotify enforces RFC 8252's
loopback-IP-literal requirement for native/installed apps and rejects
"localhost" outright on many app registrations (confirmed live).

Google Calendar: a "Desktop app" OAuth client (per .env.example's
instructions) accepts any http://localhost:* or http://127.0.0.1:*
redirect automatically -- nothing to pre-register.
"""
from __future__ import annotations

import http.server
import os
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

REDIRECT_PORT = 8765
# 127.0.0.1, not "localhost" -- see module docstring: Spotify enforces
# RFC 8252's loopback-IP-literal requirement and rejects the hostname
# outright on many app registrations (confirmed live). The HTTP server
# below binds "localhost" regardless, which resolves to the same loopback
# interface either way -- only the redirect_uri string sent to the
# provider (and pre-registered in its dashboard) needs to be the IP form.
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/callback"

PROVIDERS = {
    "spotify": {
        "client_id_env": "SPOTIFY_CLIENT_ID",
        "client_secret_env": "SPOTIFY_CLIENT_SECRET",
        "auth_url": "https://accounts.spotify.com/authorize",
        "token_url": "https://accounts.spotify.com/api/token",
        "scope": "user-modify-playback-state user-read-playback-state",
        "extra_auth_params": {},
        "token_auth": "basic",  # client_id:client_secret as HTTP Basic
    },
    "google_calendar": {
        "client_id_env": "GOOGLE_CALENDAR_CLIENT_ID",
        "client_secret_env": "GOOGLE_CALENDAR_CLIENT_SECRET",
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "https://www.googleapis.com/auth/calendar",
        # access_type=offline gets a refresh token at all; prompt=consent
        # forces Google to actually issue one even if you'd previously
        # granted this app access (otherwise it silently omits it on a
        # repeat consent).
        "extra_auth_params": {"access_type": "offline", "prompt": "consent"},
        "token_auth": "post",  # client_id/client_secret in the POST body
    },
}

_captured_code: Optional[str] = None
_captured_error: Optional[str] = None


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 -- required name by http.server
        global _captured_code, _captured_error
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        _captured_code = params.get("code", [None])[0]
        _captured_error = params.get("error", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        message = "Authorized -- you can close this tab and go back to the terminal." if _captured_code else f"Authorization failed: {_captured_error}"
        self.wfile.write(f"<html><body><h2>{message}</h2></body></html>".encode())

    def log_message(self, *args):
        pass  # quiet -- the terminal output below is the real status


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in PROVIDERS:
        print(f"Usage: python {sys.argv[0]} <{'|'.join(PROVIDERS)}>")
        sys.exit(1)

    provider = sys.argv[1]
    cfg = PROVIDERS[provider]
    client_id = os.getenv(cfg["client_id_env"])
    client_secret = os.getenv(cfg["client_secret_env"])
    if not client_id or not client_secret:
        print(f"Missing {cfg['client_id_env']} / {cfg['client_secret_env']} in .env -- set those first.")
        sys.exit(1)

    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), _CallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": cfg["scope"],
        **cfg["extra_auth_params"],
    }
    auth_url = f"{cfg['auth_url']}?{urllib.parse.urlencode(params)}"
    print(f"Opening your browser to authorize {provider}...\nIf it doesn't open automatically: {auth_url}\n")
    webbrowser.open(auth_url)

    # 480s, not 180s: a freshly-created Google OAuth client has a real,
    # documented propagation delay (confirmed live -- Google's own consent
    # screen told the user to wait ~5 minutes before it would even let the
    # flow proceed) on top of however long actually clicking through takes.
    thread.join(timeout=480)
    server.server_close()

    if _captured_error:
        print(f"Authorization failed: {_captured_error}")
        sys.exit(1)
    if not _captured_code:
        print("Timed out waiting for authorization (480s). Try again.")
        sys.exit(1)

    token_data = {
        "grant_type": "authorization_code",
        "code": _captured_code,
        "redirect_uri": REDIRECT_URI,
    }
    kwargs = {"data": token_data}
    if cfg["token_auth"] == "basic":
        kwargs["auth"] = (client_id, client_secret)
    else:
        token_data["client_id"] = client_id
        token_data["client_secret"] = client_secret

    resp = httpx.post(cfg["token_url"], **kwargs, timeout=15.0)
    if resp.status_code != 200:
        print(f"Token exchange failed ({resp.status_code}): {resp.text}")
        sys.exit(1)

    tokens = resp.json()
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print(
            "No refresh_token in the response -- for Google this usually means you'd already "
            "granted access before without revoking it first. Revoke access at "
            "https://myaccount.google.com/permissions and try again."
            if provider == "google_calendar" else
            f"No refresh_token in the response: {tokens}"
        )
        sys.exit(1)

    env_var = {"spotify": "SPOTIFY_REFRESH_TOKEN", "google_calendar": "GOOGLE_CALENDAR_REFRESH_TOKEN"}[provider]
    print(f"\nSuccess. Add this to .env:\n\n{env_var}={refresh_token}\n")


if __name__ == "__main__":
    main()
