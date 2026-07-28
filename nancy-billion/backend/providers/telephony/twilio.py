"""Real Twilio telephony adapter -- ported from OpenClaw's voice-call
extension (Twilio is the reference vendor; Telnyx/Plivo would follow the
identical TelephonyProvider shape). Uses Twilio's real REST API directly via
httpx (HTTP Basic Auth: Account SID as username, Auth Token as password) --
no twilio SDK dependency, matching this codebase's httpx-everywhere
convention for vendor calls.

place_call() uses Twilio's inline `Twiml` parameter (a real, documented
feature -- see https://www.twilio.com/docs/voice/make-calls) so a call can
actually speak real text via <Say> without needing a public webhook server
to host TwiML instructions, which would be a much heavier prerequisite for
a personal single-user assistant to stand up.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict
from xml.sax.saxutils import escape

import httpx

from providers.base import TelephonyProvider
from providers.registry import register_if_configured

logger = logging.getLogger(__name__)

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"


def _build_say_twiml(message: str, voice: str = "Polly.Joanna") -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Say voice="{voice}">{escape(message)}</Say></Response>'


class TwilioTelephonyProvider(TelephonyProvider):
    def __init__(self) -> None:
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.from_number = os.getenv("TWILIO_FROM_NUMBER")
        if not (self.account_sid and self.auth_token and self.from_number):
            raise RuntimeError("TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN/TWILIO_FROM_NUMBER not fully set")

    async def place_call(self, to_number: str, **kw: Any) -> Dict[str, Any]:
        message = kw.get("message", "This is Nancy calling.")
        twiml = kw.get("twiml") or _build_say_twiml(message, voice=kw.get("voice", "Polly.Joanna"))
        url = f"{TWILIO_API_BASE}/Accounts/{self.account_sid}/Calls.json"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    url,
                    data={"To": to_number, "From": self.from_number, "Twiml": twiml},
                    auth=(self.account_sid, self.auth_token),
                )
                resp.raise_for_status()
                data = resp.json()
                return {"success": True, "call_id": data.get("sid"), "status": data.get("status")}
        except httpx.HTTPStatusError as e:
            return {"success": False, "error": f"Twilio API error {e.response.status_code}: {e.response.text[:300]}"}
        except Exception as e:
            logger.warning("TwilioTelephonyProvider: place_call failed: %s", e)
            return {"success": False, "error": str(e)}

    async def send_sms(self, to_number: str, message: str) -> Dict[str, Any]:
        url = f"{TWILIO_API_BASE}/Accounts/{self.account_sid}/Messages.json"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    url,
                    data={"To": to_number, "From": self.from_number, "Body": message},
                    auth=(self.account_sid, self.auth_token),
                )
                resp.raise_for_status()
                data = resp.json()
                return {"success": True, "message_id": data.get("sid"), "status": data.get("status")}
        except httpx.HTTPStatusError as e:
            return {"success": False, "error": f"Twilio API error {e.response.status_code}: {e.response.text[:300]}"}
        except Exception as e:
            logger.warning("TwilioTelephonyProvider: send_sms failed: %s", e)
            return {"success": False, "error": str(e)}

    async def get_call_status(self, call_id: str) -> Dict[str, Any]:
        url = f"{TWILIO_API_BASE}/Accounts/{self.account_sid}/Calls/{call_id}.json"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, auth=(self.account_sid, self.auth_token))
                resp.raise_for_status()
                data = resp.json()
                return {"success": True, "status": data.get("status"), "duration": data.get("duration")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def end_call(self, call_id: str) -> Dict[str, Any]:
        url = f"{TWILIO_API_BASE}/Accounts/{self.account_sid}/Calls/{call_id}.json"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, data={"Status": "completed"}, auth=(self.account_sid, self.auth_token))
                resp.raise_for_status()
                return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}


register_if_configured("telephony", "twilio", "TWILIO_ACCOUNT_SID", TwilioTelephonyProvider)
