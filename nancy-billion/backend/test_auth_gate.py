"""Check the blanket auth gate, its exemptions, and WebSocket tickets.

The gate this covers replaced per-route `Depends(require_auth)`, which left 73
of 184 HTTP routes uncovered -- including POST /cron/jobs (persistent script
execution) and GET /memory/conversations/search (every word ever said to
Billion). The point of a middleware allowlist is that a route added tomorrow is
protected without anyone remembering to protect it, so that's what this asserts.

main_new.py can't be imported without the full backend environment, so this
lifts the real middleware source out of the file and drives it with stand-in
request objects. No fastapi install needed, and an edit to the gate is an edit
to what runs here.

    python backend/test_auth_gate.py
"""
from __future__ import annotations

import asyncio
import secrets as _secrets
import sys
import time as _time
from pathlib import Path
from typing import Dict, Optional

SRC = (Path(__file__).parent / "main_new.py").read_text(encoding="utf-8")


def extract(start: str, end: str) -> str:
    i = SRC.index(start)
    return SRC[i:SRC.index(end, i)]


policy_src = extract("_AUTH_EXEMPT_PATHS = {", '@app.middleware("http")')
gate_src = extract("async def _enforce_auth", '@app.get("/auth/check")')
ticket_src = extract("_WS_TICKET_TTL_S = ", '@app.post("/auth/ws-ticket")')

TOKEN = "test-token-value"


class _FakeResponse:
    def __init__(self, content=None, status_code: int = 200):
        self.status_code = status_code
        self.content = content


class _FakeRequest:
    """Only the surface the middleware actually touches."""

    def __init__(self, path: str, token: Optional[str] = None,
                 query_token: Optional[str] = None, raw_header: Optional[str] = None):
        self.url = type("U", (), {"path": path})()
        self.client = type("C", (), {"host": "10.0.0.5"})()
        headers = {}
        if raw_header is not None:
            headers["authorization"] = raw_header
        elif token is not None:
            headers["authorization"] = f"Bearer {token}"
        self.headers = headers
        self.query_params = {"token": query_token} if query_token else {}


ns: Dict = {
    "JSONResponse": lambda content, status_code=200: _FakeResponse(content, status_code),
    "secrets": _secrets,
    "_time": _time,
    "Dict": Dict,
    "_BACKEND_AUTH_TOKEN": TOKEN,
    "_rate_limiter": type("RL", (), {"check": staticmethod(lambda key: True)})(),
    "_record_security_failure": lambda *a, **k: None,
}
exec(compile(policy_src + "\n" + ticket_src + "\n" + gate_src, "main_new.py:gate", "exec"), ns)

_enforce_auth = ns["_enforce_auth"]
_is_auth_exempt = ns["_is_auth_exempt"]


async def call_next(_request):
    return _FakeResponse({"reached": True}, 200)


def status(path: str, **kw) -> int:
    """Run the real middleware and report what the caller would receive."""
    return asyncio.run(_enforce_auth(_FakeRequest(path, **kw), call_next)).status_code


failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  ok  {label}")
    else:
        failures.append(label)
        print(f"  FAIL {label}{': ' + detail if detail else ''}")


print("auth gate")

# --- exempt routes stay open ------------------------------------------------
check("/health stays open for the container healthcheck", status("/health") == 200)
check("/system/health stays open for dashboards and the CLI probe",
      status("/system/health") == 200)
check("/config/public stays open so a client can ask whether auth is on",
      status("/config/public") == 200)

# --- everything else is closed by default -----------------------------------
SENSITIVE = [
    "/memory/conversations/search",   # every word ever said to Billion
    "/cron/jobs",                     # persistent script execution
    "/config/keys",                   # writes provider keys to .env
    "/files/read",                    # the API-key leak
    "/safety/arm",                    # the keystone gate
    "/a/route/added/tomorrow",        # nobody remembered to protect this one
]
for path in SENSITIVE:
    check(f"{path} is refused without a token", status(path) == 401, str(status(path)))
    check(f"{path} works with the token", status(path, token=TOKEN) == 200)

# --- bad tokens ---------------------------------------------------------------
check("a wrong token is refused", status("/cron/jobs", token="nope") == 401)
check("a token without the Bearer prefix is refused",
      status("/cron/jobs", raw_header=TOKEN) == 401)
check("a prefix of the real token is refused", status("/cron/jobs", token=TOKEN[:-1]) == 401)
check("an empty bearer is refused", status("/cron/jobs", token="") == 401)
check("the token may be passed as a query param",
      status("/cron/jobs", query_token=TOKEN) == 200)
check("a wrong query param is refused", status("/cron/jobs", query_token="nope") == 401)

# --- rate limiting still applies ahead of auth --------------------------------
ns["_rate_limiter"] = type("RL", (), {"check": staticmethod(lambda key: False)})()
check("a rate-limited caller gets 429, not a 401 oracle",
      status("/cron/jobs", token=TOKEN) == 429)
ns["_rate_limiter"] = type("RL", (), {"check": staticmethod(lambda key: True)})()

# --- webhook prefix authenticates by HMAC, not by this gate -------------------
check("inbound webhook firing is exempt (it carries its own HMAC)",
      _is_auth_exempt("/webhooks/inbound/abc123") is True)
check("webhook *creation* is NOT exempt", _is_auth_exempt("/webhooks/inbound") is False)
check("a path merely starting with an exempt name is not exempt",
      _is_auth_exempt("/healthzzz") is False)

# --- websocket tickets --------------------------------------------------------
mint, redeem = ns["_mint_ws_ticket"], ns["_redeem_ws_ticket"]
t = mint()
check("a fresh ticket is accepted", redeem(t) is True)
check("the same ticket is refused a second time -- single use", redeem(t) is False)
check("a made-up ticket is refused", redeem("not-a-ticket") is False)
check("an empty ticket is refused", redeem("") is False)
check("two tickets are distinct", mint() != mint())

expired = mint()
ns["_ws_tickets"][expired] = _time.time() - 1
check("an expired ticket is refused", redeem(expired) is False)

# --- with no token configured, nothing changes -------------------------------
ns["_BACKEND_AUTH_TOKEN"] = ""
check("an unset token leaves every route open, exactly as before",
      status("/a/route/added/tomorrow") == 200)
check("...including the sensitive ones -- localhost setups are unaffected",
      status("/files/read") == 200)

print()
if failures:
    print(f"{len(failures)} check(s) failed")
    sys.exit(1)
print("all auth gate checks passed")
