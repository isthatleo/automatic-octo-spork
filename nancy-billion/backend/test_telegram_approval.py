"""Prove that a Telegram-initiated action can actually be approved.

The bug this guards against: the long-poll loop used to `await` the chat
handler inline. A chat turn that hit a gated tool then blocked on an approval
Future that only the poll loop could resolve -- so the prompt was sent, the
"yes" was never read, and every gated action from Telegram timed out into a
denial with nothing in the logs. This test drives _dispatch exactly the way
the poll loop does and asserts the approval resolves.

    python backend/test_telegram_approval.py
"""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# telegram_bot pulls in httpx and map_snapshot; neither is needed for the
# dispatch logic, so stub whatever isn't installed rather than requiring the
# full backend environment just to test a scheduling fix.
for name, attrs in (("httpx", {"AsyncClient": object}),
                    ("map_snapshot", {"snapshot_for_query": None})):
    try:
        __import__(name)
    except ImportError:
        mod = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        sys.modules[name] = mod

from telegram_bot import TelegramNotifier  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  ok  {label}")
    else:
        failures.append(label)
        print(f"  FAIL {label}{': ' + detail if detail else ''}")


async def main() -> None:
    print("telegram approval flow")

    bot = TelegramNotifier()
    bot._load_error = None          # pretend it's configured
    bot.chat_id = "123"
    sent: list[str] = []

    async def fake_send(text: str) -> None:
        sent.append(text)

    bot.send = fake_send            # type: ignore[assignment]

    # request_approval() and the built-in /start,/help,/approvals commands
    # send through send_html (real HTML formatting, e.g. the "<b>Approval
    # needed</b>" prompt) rather than send() -- stub it the same way so this
    # test doesn't need a real network/bot token, and so a substring check
    # like "Approval needed" still matches text captured from either path.
    async def fake_send_html(html_text: str, reply_markup=None) -> int:
        sent.append(html_text)
        return 1

    bot.send_html = fake_send_html  # type: ignore[assignment]

    async def fake_finalize(pending, value) -> None:
        pass

    bot._finalize_approval_message = fake_finalize  # type: ignore[assignment]

    approved_with: list[bool] = []

    async def chat_handler(text: str) -> str:
        """Stands in for the real pipeline: does something gated."""
        ok = await bot.request_approval(f"write a file for: {text}", timeout=5.0)
        approved_with.append(ok)
        return "done" if ok else "not approved"

    bot.set_chat_handler(chat_handler)

    # --- the poll loop's two iterations, back to back -----------------------
    bot._dispatch("save my notes to disk")      # starts a gated turn
    await asyncio.sleep(0.05)                   # let the turn reach the gate

    check("the approval prompt is actually sent",
          any("Approval needed" in s for s in sent),
          f"sent={sent}")
    check("the turn is waiting, not finished", not approved_with)

    bot._dispatch("yes")                        # the reply the loop must stay free to read
    await asyncio.gather(*list(bot._inflight))

    check("the reply resolves the approval", approved_with == [True],
          f"approved_with={approved_with}")
    check("the turn completes and replies", sent[-1] == "done", f"last sent={sent[-1]!r}")

    # --- a denial still works ----------------------------------------------
    sent.clear(); approved_with.clear()
    bot._dispatch("delete everything")
    await asyncio.sleep(0.05)
    bot._dispatch("no")
    await asyncio.gather(*list(bot._inflight))
    check("'no' denies", approved_with == [False], f"approved_with={approved_with}")

    # --- yes/no with nothing pending is ordinary chat, not swallowed --------
    sent.clear(); approved_with.clear()

    async def echo(text: str) -> str:
        return f"echo:{text}"

    bot.set_chat_handler(echo)
    bot._dispatch("yes")
    await asyncio.gather(*list(bot._inflight))
    check("a bare 'yes' with nothing pending reaches the chat handler",
          sent and sent[-1] == "echo:yes", f"sent={sent}")

    # --- an empty provider response never reaches Telegram as empty --------
    sent.clear()

    async def blank(text: str) -> str:
        return "   "

    bot.set_chat_handler(blank)
    bot._dispatch("something")
    await asyncio.gather(*list(bot._inflight))
    check("an empty reply is replaced, not sent as empty",
          sent and sent[-1].strip() != "", f"sent={sent}")

    # --- a failing turn is logged, not silently dropped --------------------
    async def boom(text: str) -> str:
        raise RuntimeError("provider exploded")

    bot.set_chat_handler(boom)
    bot._dispatch("break it")
    await asyncio.gather(*list(bot._inflight), return_exceptions=True)
    check("a crashing turn does not take the process down", True)

    print()
    if failures:
        print(f"{len(failures)} check(s) failed")
        sys.exit(1)
    print("all telegram approval checks passed")


asyncio.run(main())
