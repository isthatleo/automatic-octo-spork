"""Telegram integration for remote chat, notifications, and approvals.

Lets Nancy reach you via Telegram when you're away from the PC, and lets you
chat with her directly from Telegram:
- Two-way chat: any message that isn't a yes/no reply to a pending approval
  is routed through the same chat pipeline as the app (set via
  `set_chat_handler`), with the reply sent back to you.
- Selective image attachments: if your message looks like a location/map
  query (see `_extract_location_query`), the reply is sent as a photo (a real
  map snapshot via map_snapshot.py) with the text as its caption -- not for
  every reply, just where a picture actually helps.
- Push notifications (e.g. a long-running agent task finishing) and a simple
  approve/deny gate for higher-risk actions, with your reply read back via
  long polling (no public webhook/HTTPS endpoint needed).

Setup: create a bot via @BotFather, message it once, then set
TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (your own chat id, read from
getUpdates after messaging the bot) in .env.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Awaitable, Callable, Dict, Optional

import httpx

from map_snapshot import snapshot_for_query

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"

ChatHandler = Callable[[str], Awaitable[str]]

_LOCATION_RE = re.compile(
    r"\b(?:locate|find|show me|show|go to|where(?:'s| is)|directions? to|map of|navigate to|take me to)\s+(.+)",
    re.IGNORECASE,
)


def _extract_location_query(text: str) -> Optional[str]:
    """Best-effort extraction of a place name from a location-style query,
    mirroring frontend/lib/nancy/commands.ts's LOCATE regex so 'a map/direction
    request' means the same thing here as it does in the voice/text UI."""
    m = _LOCATION_RE.search(text)
    if not m:
        return None
    query = m.group(1).strip().rstrip("?.!,")
    return query or None


class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self._client: Optional[httpx.AsyncClient] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._last_update_id = 0
        # request_id -> Future[bool], resolved True/False when a yes/no reply arrives.
        # Ordered dict semantics (insertion order) let us resolve the oldest
        # outstanding request first -- fine for this single-user assistant.
        self._pending_approvals: Dict[str, "asyncio.Future[bool]"] = {}
        self._chat_handler: Optional[ChatHandler] = None
        self._load_error: Optional[str] = None
        if not self.token or not self.chat_id:
            self._load_error = "TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not configured"

    def set_chat_handler(self, handler: ChatHandler) -> None:
        """Register the function that turns free-form Telegram messages into
        replies -- main_new.py wires this to the same chat pipeline the
        voice/web UI uses (_generate_response_via_hierarchy), set after both
        modules are loaded to avoid a circular import."""
        self._chat_handler = handler

    @property
    def status(self) -> dict:
        return {"available": self._load_error is None, "error": self._load_error}

    def _client_or_raise(self) -> httpx.AsyncClient:
        if self._load_error:
            raise RuntimeError(self._load_error)
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=f"{TELEGRAM_API}/bot{self.token}", timeout=30.0)
        return self._client

    async def send(self, text: str) -> None:
        """Push a message to your Telegram. Best-effort: logs and returns on
        failure rather than raising, since a notification failing shouldn't
        break whatever triggered it."""
        if self._load_error:
            logger.warning("Telegram send skipped: %s", self._load_error)
            return
        try:
            client = self._client_or_raise()
            resp = await client.post("/sendMessage", data={"chat_id": self.chat_id, "text": text})
            resp.raise_for_status()
        except Exception as e:
            logger.error("Telegram send failed: %s", e)

    async def send_document(self, file_bytes: bytes, filename: str, caption: str = "") -> None:
        """Send a file with an optional caption, uncompressed. Best-effort,
        same failure handling as send(). Used instead of send_photo for
        images where full resolution matters (Telegram's sendPhoto silently
        downscales anything above ~1280px on the long side; sendDocument
        preserves the original bytes so the recipient can zoom into detail)."""
        if self._load_error:
            logger.warning("Telegram send_document skipped: %s", self._load_error)
            return
        try:
            client = self._client_or_raise()
            resp = await client.post(
                "/sendDocument",
                data={"chat_id": self.chat_id, "caption": caption[:1024]},
                files={"document": (filename, file_bytes, "application/octet-stream")},
                timeout=60.0,
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error("Telegram send_document failed: %s", e)

    async def request_approval(self, action_description: str, timeout: float = 300.0) -> bool:
        """Send an approval request and wait for a yes/no reply. Defaults to
        False (deny) on timeout or if Telegram isn't configured -- a
        higher-risk action should never proceed just because nobody was
        reachable to approve it."""
        if self._load_error:
            logger.warning("Approval gate defaulting to deny (Telegram unavailable): %s", self._load_error)
            return False

        request_id = f"appr-{int(time.time() * 1000)}"
        future: "asyncio.Future[bool]" = asyncio.get_event_loop().create_future()
        self._pending_approvals[request_id] = future
        await self.send(
            f"Approval needed:\n\n{action_description}\n\n"
            f"Reply 'yes' or 'no' (times out in {int(timeout)}s -> denied)."
        )
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            logger.info("Approval request %s timed out, defaulting to deny", request_id)
            return False
        finally:
            self._pending_approvals.pop(request_id, None)

    def start_polling(self) -> None:
        """Start the long-poll loop that reads your replies. Call once at
        app startup, inside a running event loop."""
        if self._load_error or self._poll_task is not None:
            return
        self._poll_task = asyncio.get_event_loop().create_task(self._poll_loop())
        logger.info("Telegram polling started (chat_id=%s)", self.chat_id)

    async def stop_polling(self) -> None:
        if self._poll_task is not None:
            self._poll_task.cancel()
            self._poll_task = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _poll_loop(self) -> None:
        client = self._client_or_raise()
        while True:
            try:
                resp = await client.get(
                    "/getUpdates",
                    params={"offset": self._last_update_id + 1, "timeout": 25},
                )
                data = resp.json()
                for update in data.get("result", []):
                    self._last_update_id = max(self._last_update_id, update["update_id"])
                    message = update.get("message")
                    if not message:
                        continue
                    if str(message.get("chat", {}).get("id")) != str(self.chat_id):
                        continue  # ignore anyone but the configured user
                    text = (message.get("text") or "").strip()
                    if text:
                        await self._handle_reply(text)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("Telegram poll error: %s", e)
                await asyncio.sleep(5)

    async def _handle_reply(self, text: str) -> None:
        lowered = text.lower()
        # Only consume a bare "yes"/"no" as an approval reply if something is
        # actually pending -- otherwise casual chat like "no thanks" or "yes,
        # go on" would be silently swallowed instead of reaching the chat
        # handler.
        if self._pending_approvals:
            if lowered in ("yes", "y", "approve", "approved"):
                self._resolve_oldest_pending(True)
                return
            if lowered in ("no", "n", "deny", "denied"):
                self._resolve_oldest_pending(False)
                return

        # Not an approval reply -- treat it as a chat message.
        if self._chat_handler is None:
            await self.send("Chat isn't connected yet on this deployment.")
            return

        try:
            reply = await self._chat_handler(text)
        except Exception as e:
            logger.error("Telegram chat handler failed: %s", e)
            await self.send("Sorry, I hit an error working on that.")
            return

        # Only attach an image for location/map-style queries -- not every reply.
        location_query = _extract_location_query(text)
        if location_query:
            snapshot = await snapshot_for_query(location_query)
            if snapshot is not None:
                image_bytes, display_name, was_night = snapshot
                prefix = "\U0001f319 Night view" if was_night else "\U0001f6f0 Satellite view"
                caption = f"{reply}\n\n{prefix} · {display_name}"
                await self.send_document(image_bytes, filename="snapshot.png", caption=caption)
                return

        await self.send(reply)

    def _resolve_oldest_pending(self, value: bool) -> None:
        if not self._pending_approvals:
            return
        request_id = next(iter(self._pending_approvals))
        future = self._pending_approvals.get(request_id)
        if future and not future.done():
            future.set_result(value)


telegram_notifier = TelegramNotifier()
