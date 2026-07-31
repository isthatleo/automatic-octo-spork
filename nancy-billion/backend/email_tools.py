"""Real email send/receive via plain SMTP/IMAP -- stdlib only (smtplib,
imaplib, email), no vendor SDK or new dependency. Confirmed live (2026-07-31
Hermes-parity audit): Nancy had no email capability at all, unlike Hermes'
"send/receive email via Himalaya CLI" skill. This covers the same ground
generically (any real SMTP/IMAP provider -- Gmail, Outlook, a private mail
server, etc. via app-password auth) rather than shelling out to a specific
CLI tool, consistent with how every other credentialed capability in this
codebase degrades gracefully when its env vars are absent (see llm.py's
get_llm_backends(), providers/registry.py's register_if_configured).

Sending is approval-gated in main_new.py's dispatcher (same tier as
send_sms/place_phone_call -- real outbound communication a user should
confirm). Reading is not (same tier as take_screenshot -- read-only).
"""
from __future__ import annotations

import email.utils
import imaplib
import logging
import os
import smtplib
from email.message import EmailMessage
from email.header import decode_header
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

EMAIL_TOOLS = [
    {
        "name": "send_email",
        "description": (
            "Send a real email via the configured SMTP account. Requires the user's explicit "
            "yes/no approval before it sends. Not available if no email account is configured."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient address."},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "list_recent_emails",
        "description": (
            "List real recent emails from the configured IMAP inbox (subject, sender, date, a "
            "short preview) -- read-only, no approval needed. Not available if no email account "
            "is configured."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Default 10, max 25."},
                "unread_only": {"type": "boolean"},
            },
        },
    },
]


def send_email(to: str, subject: str, body: str) -> Dict[str, Any]:
    address = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_PASSWORD")
    if not address or not password:
        return {"success": False, "error": "Email is not configured (set EMAIL_ADDRESS and EMAIL_PASSWORD)."}

    smtp_host = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))

    msg = EmailMessage()
    msg["From"] = address
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg.set_content(body)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            server.starttls()
            server.login(address, password)
            server.send_message(msg)
        return {"success": True, "to": to, "subject": subject}
    except Exception as e:
        logger.warning("send_email: failed: %s", e)
        return {"success": False, "error": str(e)}


def _decode(value: Optional[str]) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            out.append(text.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(text)
    return " ".join(out)


def list_recent_emails(limit: int = 10, unread_only: bool = False) -> Dict[str, Any]:
    address = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_PASSWORD")
    if not address or not password:
        return {"success": False, "error": "Email is not configured (set EMAIL_ADDRESS and EMAIL_PASSWORD)."}

    limit = max(1, min(int(limit or 10), 25))
    imap_host = os.getenv("EMAIL_IMAP_HOST", "imap.gmail.com")
    imap_port = int(os.getenv("EMAIL_IMAP_PORT", "993"))

    try:
        with imaplib.IMAP4_SSL(imap_host, imap_port, timeout=20) as conn:
            conn.login(address, password)
            conn.select("INBOX", readonly=True)
            criterion = "UNSEEN" if unread_only else "ALL"
            status, data = conn.search(None, criterion)
            if status != "OK":
                return {"success": False, "error": "IMAP search failed"}
            ids = data[0].split()[-limit:][::-1]  # most recent first

            messages: List[Dict[str, Any]] = []
            for msg_id in ids:
                status, msg_data = conn.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw_header = msg_data[0][1]
                import email as email_module
                parsed = email_module.message_from_bytes(raw_header)
                messages.append({
                    "from": _decode(parsed.get("From")),
                    "subject": _decode(parsed.get("Subject")),
                    "date": parsed.get("Date", ""),
                })
        return {"success": True, "count": len(messages), "emails": messages}
    except Exception as e:
        logger.warning("list_recent_emails: failed: %s", e)
        return {"success": False, "error": str(e)}
