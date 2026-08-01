"""Telegram integration for remote chat, notifications, and approvals.

Lets Nancy reach you via Telegram when you're away from the PC, and lets you
chat with her directly from Telegram:
- Two-way chat: any message that isn't a yes/no reply to a pending approval
  and doesn't start with "/" is routed through the same chat pipeline as the
  app (set via `set_chat_handler`), with the reply sent back to you.
- A real command menu (/start, /help, /status, /markets, /approvals) backed
  by Telegram's native command list (so it shows up in the client's "/"
  picker), plus inline-keyboard quick actions on the /start message that
  fire the same commands with a tap.
- Approvals use real inline-keyboard buttons (✅ Approve / ❌ Deny) resolved
  via callback_query, not a typed "yes"/"no" reply -- typing yes/no still
  works too, for accessibility, and resolves whichever approval is oldest.
- A native "typing..." indicator is kept alive for the whole time a chat
  reply or command is being composed, refreshed every 4s since Telegram
  clears it after ~5s on its own.
- Selective image attachments: if your message looks like a location/map
  query (see `_extract_location_query`), the reply is sent as a photo (a real
  map snapshot via map_snapshot.py) with the text as its caption -- not for
  every reply, just where a picture actually helps.
- Push notifications (e.g. a long-running agent task finishing), with your
  reply read back via long polling (no public webhook/HTTPS endpoint needed).

Setup: create a bot via @BotFather, message it once, then set
TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (your own chat id, read from
getUpdates after messaging the bot) in .env.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Optional

import httpx

from map_snapshot import snapshot_for_query

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"

ChatHandler = Callable[[str], Awaitable[str]]
# A registered /command's handler takes the raw text after the command name
# (e.g. "a golden retriever wearing sunglasses" for "/image a golden
# retriever wearing sunglasses", "" if no args were given) and returns
# HTML-ready text (Telegram's HTML parse_mode) -- the caller (main_new.py)
# is responsible for escaping any dynamic substring that could contain "<",
# ">", or "&" via _escape_html, same contract as the rest of this module's
# internally-built messages. A handler that needs to send more than text
# (e.g. a generated image) sends it directly via telegram_notifier and
# returns a short confirmation string.
CommandHandler = Callable[[str], Awaitable[str]]

_LOCATION_RE = re.compile(
    r"\b(?:locate|find|show me|show|go to|where(?:'s| is)|directions? to|map of|navigate to|take me to)\s+(.+)",
    re.IGNORECASE,
)

# The single source of truth for both Telegram's native "/" command picker
# (setMyCommands) and /help's listing -- "status" and "markets" are wired to
# real backend data by main_new.py via set_command_handler; "start", "help",
# and "approvals" are built-in since they only need this module's own state.
_BUILTIN_COMMANDS = [
    ("start", "Quick actions & welcome"),
    ("help", "List everything I can do"),
    ("status", "Real-time agent & system status"),
    ("markets", "Live snapshot of your watched pairs"),
    ("approvals", "See what's waiting on your approval"),
    ("image", "Generate an image -- /image a description"),
    ("recall", "Search your memory -- /recall a topic"),
    ("coworkers", "See what background tasks are being worked on"),
    ("tasks", "See the last proactive agent task batch"),
]


def _extract_location_query(text: str) -> Optional[str]:
    """Best-effort extraction of a place name from a location-style query,
    mirroring frontend/lib/nancy/commands.ts's LOCATE regex so 'a map/direction
    request' means the same thing here as it does in the voice/text UI."""
    m = _LOCATION_RE.search(text)
    if not m:
        return None
    query = m.group(1).strip().rstrip("?.!,")
    return query or None


_INFO_PLACE_RE = re.compile(
    r"\b(?:history of|brief history of|background of|tell me about|what do you know about|information about|facts about)\s+(.+)",
    re.IGNORECASE,
)


def _extract_info_place_query(text: str) -> Optional[str]:
    """Best-effort extraction of a place name from an INFORMATIONAL question
    ('history of Rome', 'tell me about Kyoto') -- distinct from
    _extract_location_query's action-oriented phrasing ('locate Rome', 'show
    me Kyoto'). Whether the extracted phrase is actually a real place (as
    opposed to 'tell me about jazz') is left entirely to snapshot_for_query's
    own real geocoding lookup, which simply returns None for anything that
    doesn't resolve -- so a non-place topic never needs special-casing here."""
    m = _INFO_PLACE_RE.search(text)
    if not m:
        return None
    query = m.group(1).strip().rstrip("?.!,")
    # Trims a trailing "'s history"/"'s background" some phrasings leave behind.
    query = re.sub(r"['’]s\s+(history|background|story)$", "", query, flags=re.IGNORECASE).strip()
    return query or None


def _escape_html(text: str) -> str:
    """Escape the 3 characters Telegram's HTML parse_mode treats specially.
    Every plain-text message this module sends goes through this before
    being sent with parse_mode=HTML, so a caller passing an ordinary string
    (as all ~30 existing call sites in main_new.py do) renders identically
    to before -- HTML mode is purely additive, only used intentionally by
    this module's own richly-formatted messages (welcome, help, status,
    markets, approval prompts)."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@dataclass
class _PendingApproval:
    future: "asyncio.Future[bool]"
    description: str
    body_html: str
    message_id: Optional[int] = None


class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self._client: Optional[httpx.AsyncClient] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._last_update_id = 0
        # request_id -> pending approval state, resolved when a button tap
        # (callback_query) or a typed yes/no reply arrives. Ordered dict
        # semantics (insertion order) let the typed-reply path resolve the
        # oldest outstanding request -- a button tap instead resolves its
        # own specific request_id directly, since callback_data carries it.
        self._pending_approvals: Dict[str, _PendingApproval] = {}
        self._chat_handler: Optional[ChatHandler] = None
        self._command_handlers: Dict[str, CommandHandler] = {}
        self._image_broadcaster: Optional[Callable[[bytes, str], Awaitable[None]]] = None
        self._load_error: Optional[str] = None
        # In-flight chat turns spawned off the poll loop. Held in a set purely
        # so the event loop keeps a strong reference -- asyncio only keeps a
        # weak one, so an un-stored task can be garbage-collected mid-turn.
        self._inflight: set["asyncio.Task"] = set()
        if not self.token or not self.chat_id:
            self._load_error = "TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not configured"

    def set_chat_handler(self, handler: ChatHandler) -> None:
        """Register the function that turns free-form Telegram messages into
        replies -- main_new.py wires this to the same chat pipeline the
        voice/web UI uses (_generate_response_via_hierarchy), set after both
        modules are loaded to avoid a circular import."""
        self._chat_handler = handler

    def set_command_handler(self, command: str, handler: CommandHandler) -> None:
        """Register a /command's real reply -- main_new.py wires /status and
        /markets to real backend data here, same decoupling reasoning as
        set_chat_handler (this module never imports backend internals
        directly). "start"/"help"/"approvals" are handled internally since
        they only need this module's own state."""
        self._command_handlers[command] = handler

    def set_image_broadcaster(self, callback: Callable[[bytes, str], Awaitable[None]]) -> None:
        """Register a callback(image_bytes, caption) fired whenever this
        module sends a real image (currently: a location-query map
        snapshot) -- main_new.py wires this to broadcast the same image to
        every connected web/voice UI session, same real-conversation-sync
        reasoning as set_chat_handler above, just for images instead of
        text."""
        self._image_broadcaster = callback

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
        break whatever triggered it. Sent as escaped HTML so it renders
        identically to plain text for every existing caller, while this
        module's own richly-formatted messages can use send_html directly."""
        await self.send_html(_escape_html(text))

    async def send_html(self, html_text: str, reply_markup: Optional[dict] = None) -> Optional[int]:
        """Send a pre-built HTML-formatted message -- the caller is
        responsible for escaping any embedded dynamic/untrusted text (see
        _escape_html). Returns the sent message_id (used later to edit an
        approval prompt in place) or None on failure."""
        if self._load_error:
            logger.warning("Telegram send skipped: %s", self._load_error)
            return None
        try:
            client = self._client_or_raise()
            data: Dict[str, str] = {"chat_id": self.chat_id, "text": html_text, "parse_mode": "HTML"}
            if reply_markup is not None:
                data["reply_markup"] = json.dumps(reply_markup)
            resp = await client.post("/sendMessage", data=data)
            resp.raise_for_status()
            return resp.json().get("result", {}).get("message_id")
        except Exception as e:
            logger.error("Telegram send failed: %s", e)
            return None

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

    async def send_photo(self, image_bytes: bytes, caption: str = "") -> None:
        """Send an image as a real inline photo card -- unlike send_document
        (which preserves every pixel for zooming into detail), Telegram
        renders this directly in the chat as a proper photo, which is what
        actually looks good for something like a location-history recon
        shot. Caption is sent as HTML, same as send_html -- caller escapes
        any dynamic text it embeds."""
        if self._load_error:
            logger.warning("Telegram send_photo skipped: %s", self._load_error)
            return
        try:
            client = self._client_or_raise()
            resp = await client.post(
                "/sendPhoto",
                data={"chat_id": self.chat_id, "caption": caption[:1024], "parse_mode": "HTML"},
                files={"photo": ("snapshot.jpg", image_bytes, "image/jpeg")},
                timeout=60.0,
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error("Telegram send_photo failed: %s", e)

    async def _send_chat_action(self, action: str) -> None:
        if self._load_error:
            return
        try:
            client = self._client_or_raise()
            await client.post("/sendChatAction", data={"chat_id": self.chat_id, "action": action})
        except Exception:
            pass  # best-effort -- a missing typing indicator is never worth breaking a reply over

    async def _with_typing(self, coro: Awaitable[str]) -> str:
        """Keeps Telegram's native 'Bot is typing...' indicator alive for the
        whole time `coro` is running, refreshed every 4s -- Telegram clears
        it on its own after ~5s, and a real tool-use turn or a slow cold-
        start TTS/LLM call can easily take longer than that."""
        async def _keep_typing() -> None:
            while True:
                await self._send_chat_action("typing")
                await asyncio.sleep(4)

        keeper = asyncio.get_event_loop().create_task(_keep_typing())
        try:
            return await coro
        finally:
            keeper.cancel()

    async def request_approval(self, action_description: str, timeout: float = 300.0) -> bool:
        """Send an approval request with real ✅/❌ inline-keyboard buttons and
        wait for a decision -- a typed 'yes'/'no' reply still works too (it
        resolves whichever approval is oldest, same as before this button
        upgrade). Defaults to False (deny) on timeout or if Telegram isn't
        configured -- a higher-risk action should never proceed just because
        nobody was reachable to approve it."""
        if self._load_error:
            logger.warning("Approval gate defaulting to deny (Telegram unavailable): %s", self._load_error)
            return False

        request_id = f"appr-{int(time.time() * 1000)}"
        future: "asyncio.Future[bool]" = asyncio.get_event_loop().create_future()
        body_html = f"\U0001f510 <b>Approval needed, Sir</b>\n\n{_escape_html(action_description)}"
        pending = _PendingApproval(future=future, description=action_description, body_html=body_html)
        self._pending_approvals[request_id] = pending

        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ Approve", "callback_data": f"appr:{request_id}:yes"},
                {"text": "❌ Deny", "callback_data": f"appr:{request_id}:no"},
            ]]
        }
        pending.message_id = await self.send_html(
            f"{body_html}\n\n<i>Tap a button, or reply yes/no. Times out in {int(timeout)}s -&gt; denied.</i>",
            reply_markup=keyboard,
        )

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            logger.info("Approval request %s timed out, defaulting to deny", request_id)
            result = False
        finally:
            self._pending_approvals.pop(request_id, None)

        await self._finalize_approval_message(pending, result)
        return result

    async def _finalize_approval_message(self, pending: _PendingApproval, value: bool) -> None:
        """Edits the original approval prompt in place once resolved (button
        tap, typed reply, or timeout, all funnel through here) so it reads
        as a real decided message instead of staying an active-looking
        prompt with dead buttons."""
        if pending.message_id is None:
            return
        outcome = "✅ <b>Approved</b>" if value else "❌ <b>Denied</b>"
        try:
            client = self._client_or_raise()
            await client.post("/editMessageText", data={
                "chat_id": self.chat_id,
                "message_id": pending.message_id,
                "text": f"{pending.body_html}\n\n{outcome}",
                "parse_mode": "HTML",
            })
        except Exception as e:
            logger.warning("Telegram approval message update failed: %s", e)

    def start_polling(self) -> None:
        """Start the long-poll loop that reads your replies, and register the
        real "/" command menu. Call once at app startup, inside a running
        event loop."""
        if self._load_error or self._poll_task is not None:
            return
        self._poll_task = asyncio.get_event_loop().create_task(self._poll_loop())
        asyncio.get_event_loop().create_task(self._register_commands())
        logger.info("Telegram polling started (chat_id=%s)", self.chat_id)

    async def _register_commands(self) -> None:
        try:
            client = self._client_or_raise()
            commands = [{"command": cmd, "description": desc} for cmd, desc in _BUILTIN_COMMANDS]
            resp = await client.post("/setMyCommands", json={"commands": commands})
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Telegram setMyCommands failed: %s", e)

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
                    params={"offset": self._last_update_id + 1, "timeout": 25, "allowed_updates": '["message","callback_query"]'},
                )
                # A non-200 (commonly a 409 when a second poller overlaps
                # during a restart) yields no results, and without this the
                # loop would immediately re-request in a tight spin.
                if resp.status_code != 200:
                    logger.warning("Telegram getUpdates returned %s; backing off", resp.status_code)
                    await asyncio.sleep(5)
                    continue
                data = resp.json()
                for update in data.get("result", []):
                    self._last_update_id = max(self._last_update_id, update["update_id"])
                    callback_query = update.get("callback_query")
                    if callback_query:
                        self._dispatch_callback(callback_query)
                        continue
                    message = update.get("message")
                    if not message:
                        continue
                    if str(message.get("chat", {}).get("id")) != str(self.chat_id):
                        continue  # ignore anyone but the configured user
                    text = (message.get("text") or "").strip()
                    if text:
                        self._dispatch(text)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("Telegram poll error: %s", e)
                await asyncio.sleep(5)

    def _dispatch(self, text: str) -> None:
        """Route one incoming message without ever blocking the poll loop.

        This is load-bearing. An approval reply can ONLY be resolved from this
        loop, while a chat turn that hits a gated tool blocks waiting for that
        very reply -- so awaiting the chat handler inline deadlocked every
        gated action: the prompt arrived, "yes" was never read, and the request
        timed out into a denial with nothing in the logs to explain it.
        Approvals stay inline (they resolve a Future and return immediately);
        chat turns and commands go to a background task so the loop gets
        straight back to getUpdates.
        """
        lowered = text.lower()
        if self._pending_approvals:
            if lowered in ("yes", "y", "approve", "approved"):
                self._resolve_oldest_pending(True)
                return
            if lowered in ("no", "n", "deny", "denied"):
                self._resolve_oldest_pending(False)
                return

        if text.startswith("/"):
            command, _, args = text[1:].partition(" ")
            command = command.split("@", 1)[0].lower()  # strip the "@BotName" suffix Telegram appends in group chats
            task = asyncio.get_event_loop().create_task(self._handle_command(command, args.strip()))
        else:
            task = asyncio.get_event_loop().create_task(self._handle_reply(text))
        self._inflight.add(task)
        task.add_done_callback(self._inflight.discard)
        task.add_done_callback(self._log_task_error)

    def _dispatch_callback(self, callback_query: dict) -> None:
        """Handles an inline-keyboard button tap. Both branches answer the
        callback (clears the tapped button's loading spinner) via a
        background task so, same as _dispatch, the poll loop never blocks."""
        data = callback_query.get("data") or ""
        callback_id = callback_query.get("id")

        if data.startswith("appr:"):
            parts = data.split(":", 2)
            if len(parts) == 3:
                _, request_id, decision = parts
                pending = self._pending_approvals.get(request_id)
                if pending and not pending.future.done():
                    pending.future.set_result(decision == "yes")
            asyncio.get_event_loop().create_task(self._answer_callback(callback_id))
            return

        if data.startswith("cmd:"):
            command = data[len("cmd:"):]
            asyncio.get_event_loop().create_task(self._answer_callback(callback_id))
            task = asyncio.get_event_loop().create_task(self._handle_command(command, ""))
            self._inflight.add(task)
            task.add_done_callback(self._inflight.discard)
            task.add_done_callback(self._log_task_error)
            return

        asyncio.get_event_loop().create_task(self._answer_callback(callback_id))

    async def _answer_callback(self, callback_id: Optional[str], text: str = "") -> None:
        if not callback_id or self._load_error:
            return
        try:
            client = self._client_or_raise()
            payload: Dict[str, str] = {"callback_query_id": callback_id}
            if text:
                payload["text"] = text
            await client.post("/answerCallbackQuery", data=payload)
        except Exception:
            pass  # best-effort -- worst case the button's spinner lingers briefly

    @staticmethod
    def _log_task_error(task: "asyncio.Task") -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("Telegram chat turn failed: %s", exc, exc_info=exc)

    async def _handle_command(self, command: str, args: str) -> None:
        if command == "start":
            await self._send_start_message()
            return
        if command == "help":
            await self._send_help_message()
            return
        if command == "approvals":
            await self._send_approvals_message()
            return

        handler = self._command_handlers.get(command)
        if handler is None:
            await self.send(f"Unknown command: /{command}. Try /help.")
            return
        try:
            reply_html = await self._with_typing(handler(args))
        except Exception as e:
            logger.error("Telegram command /%s failed: %s", command, e)
            await self.send(f"Sorry, I hit an error running /{command}.")
            return
        await self.send_html(reply_html)

    async def _send_start_message(self) -> None:
        text = (
            "\U0001f44b <b>Evening, Sir.</b> I'm Nancy -- ask me anything, or tap a quick action below.\n\n"
            "I remember our conversation, keep an eye on your markets, and can act through real "
            "tools (files, trades, research) -- anything risky still comes back to you for approval."
        )
        keyboard = {"inline_keyboard": [
            [{"text": "\U0001f4ca Markets", "callback_data": "cmd:markets"}, {"text": "\U0001f4cb Status", "callback_data": "cmd:status"}],
            [{"text": "\U0001f3a8 Image", "callback_data": "cmd:image"}, {"text": "\U0001f9e0 Recall", "callback_data": "cmd:recall"}],
            [{"text": "\U0001f510 Approvals", "callback_data": "cmd:approvals"}, {"text": "❓ Help", "callback_data": "cmd:help"}],
        ]}
        await self.send_html(text, reply_markup=keyboard)

    async def _send_help_message(self) -> None:
        lines = ["<b>What I can do</b>", ""]
        for cmd, desc in _BUILTIN_COMMANDS:
            lines.append(f"/{cmd} -- {_escape_html(desc)}")
        lines.append("")
        lines.append("Or just message me anything -- I'll chat like normal, with real tools and memory behind the scenes.")
        await self.send_html("\n".join(lines))

    async def _send_approvals_message(self) -> None:
        if not self._pending_approvals:
            await self.send_html("✅ Nothing waiting on your approval right now, Sir.")
            return
        lines = ["\U0001f510 <b>Pending approvals</b>", ""]
        for pending in self._pending_approvals.values():
            lines.append(f"• {_escape_html(pending.description)}")
        await self.send_html("\n".join(lines))

    async def _handle_reply(self, text: str) -> None:
        # Approval replies are consumed by _dispatch before they ever reach
        # here, so anything arriving at this point is a genuine chat message.
        if self._chat_handler is None:
            await self.send("Chat isn't connected yet on this deployment.")
            return

        try:
            reply = await self._with_typing(self._chat_handler(text))
        except Exception as e:
            logger.error("Telegram chat handler failed: %s", e)
            await self.send("Sorry, I hit an error working on that.")
            return

        # A provider can return a successful-but-empty response. Telegram
        # rejects an empty `text` with a 400, which send() swallows -- so the
        # symptom was no reply at all, with nothing to explain it.
        if not (reply or "").strip():
            logger.warning("Chat handler returned an empty reply for: %.80s", text)
            await self.send("I didn't get a usable answer to that one, Sir. Try rephrasing?")
            return

        # A direct location COMMAND ("locate Rome", "show me Kyoto") -- the
        # map itself is the point of the request, so it goes out full-
        # resolution via send_document with the reply as its caption, same
        # as before.
        location_query = _extract_location_query(text)
        if location_query:
            snapshot = await snapshot_for_query(location_query)
            if snapshot is not None:
                image_bytes, display_name, was_night = snapshot
                prefix = "\U0001f319 Night view" if was_night else "\U0001f6f0 Satellite view"
                caption = f"{reply}\n\n{prefix} · {display_name}"
                await self.send_document(image_bytes, filename="snapshot.png", caption=caption)
                # Real conversation sync -- the web/voice UI sees this same
                # snapshot too, not just Telegram (see set_image_broadcaster).
                if self._image_broadcaster:
                    try:
                        await self._image_broadcaster(image_bytes, caption)
                    except Exception as e:
                        logger.warning("image_broadcaster failed: %s", e)
                return

        # An INFORMATIONAL question ABOUT a place ("history of Rome", "tell
        # me about Kyoto") gets a two-part card instead of one caption-
        # limited message: the full detailed answer as its own richly-
        # formatted message (Telegram's caption cap is 1024 chars -- nowhere
        # near enough for the 3-4+ paragraph replies this channel's style
        # now asks for), followed by a real satellite/night recon photo as a
        # visual follow-up. snapshot_for_query's own geocoding decides
        # whether this is actually a place at all -- a non-place topic
        # ("tell me about jazz") returns None and just falls through to the
        # plain reply below, no special-casing needed here.
        place_query = _extract_info_place_query(text)
        if place_query:
            snapshot = await snapshot_for_query(place_query)
            if snapshot is not None:
                image_bytes, display_name, was_night = snapshot
                await self.send_html(
                    f"\U0001f4d6 <b>{_escape_html(display_name)}</b>\n\n{_escape_html(reply)}"
                )
                style = "\U0001f319 Night recon" if was_night else "\U0001f6f0 Satellite recon"
                caption = f"{style} · <b>{_escape_html(display_name)}</b>"
                await self.send_photo(image_bytes, caption=caption)
                if self._image_broadcaster:
                    try:
                        await self._image_broadcaster(image_bytes, f"{style} · {display_name}")
                    except Exception as e:
                        logger.warning("image_broadcaster failed: %s", e)
                return

        await self.send(reply)

    def _resolve_oldest_pending(self, value: bool) -> None:
        """Typed yes/no fallback path (button taps resolve their own specific
        request_id directly in _dispatch_callback instead) -- fine for this
        single-user assistant where "oldest" is an unambiguous choice."""
        if not self._pending_approvals:
            return
        request_id = next(iter(self._pending_approvals))
        pending = self._pending_approvals.get(request_id)
        if pending and not pending.future.done():
            pending.future.set_result(value)


telegram_notifier = TelegramNotifier()
