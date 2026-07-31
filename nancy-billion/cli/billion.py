#!/usr/bin/env python3
"""Billion CLI -- run Billion in your terminal, Hermes-agent style.

A thin terminal surface over the SAME brain every other surface uses: the
REST /chat path now routes through the backend's full tool-use chokepoint
(_generate_response_via_hierarchy), so a terminal conversation gets the
identical tools, skills, memory, and approval gating as the web UI, voice,
and Telegram -- and shares one continuous conversation history with them.

Pure stdlib (urllib + ANSI). Python 3.9+. Zero pip installs.

Usage:
    python cli/billion.py                    # backend at localhost:8000
    BILLION_BACKEND_URL=http://host:8000 ... # remote backend
    BACKEND_AUTH_TOKEN=...                   # sent as Bearer when set

Commands: /help /status /agents /tools /skills /model [name] /memory <query> /clear /quit
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import textwrap
import threading
import time
import urllib.error
import urllib.request

VERSION = "1.0.0"
BACKEND = os.getenv("BILLION_BACKEND_URL", "http://localhost:8000").rstrip("/")
AUTH_TOKEN = os.getenv("BACKEND_AUTH_TOKEN", "")
SESSION_ID = time.strftime("%Y%m%d_%H%M%S") + "_" + os.urandom(2).hex()

# os.system('') flips modern Windows consoles into VT mode so ANSI renders.
os.system("")
# Real crash, confirmed live: Windows' Python defaults stdout/stderr to the
# legacy console codepage (cp1252 here) whenever it isn't attached to a real
# interactive terminal -- piped output, a redirected file, some CI runners --
# and the box-drawing (╭) and braille spinner (⠋) characters below
# aren't in that codepage, so the very first print() crashed with
# UnicodeEncodeError before anything ever rendered. reconfigure() is a no-op
# error if stdout has no such method (rare, older embedded interpreters).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
CYAN, GOLD, DIM, BOLD, RED, RESET = "\033[96m", "\033[93m", "\033[2m", "\033[1m", "\033[91m", "\033[0m"

# Dot-matrix reactor orb -- Billion's mark, in the same dotted style as the
# reference boot screens. Pure characters, no images.
ORB = r"""
          ·  ∙ ∙∙•••∙∙ ∙  ·
       ∙ •·∙∙∙∙•••••••∙∙∙∙·• ∙
     ∙•∙∙  ·∙••∙∙∙∙∙∙∙••∙·  ∙∙•∙
    •∙∙   ∙•∙∙  ∙•••∙  ∙∙•∙   ∙∙•
   •∙∙   ∙•∙   ∙•∙ ∙•∙   ∙•∙   ∙∙•
   •∙   ∙•∙   ∙•  ∙∙∙ •∙   ∙•∙   ∙•
   •∙∙   ∙•∙   ∙•∙ ∙•∙   ∙•∙   ∙∙•
    •∙∙   ∙•∙∙  ∙•••∙  ∙∙•∙   ∙∙•
     ∙•∙∙  ·∙••∙∙∙∙∙∙∙••∙·  ∙∙•∙
       ∙ •·∙∙∙∙•••••••∙∙∙∙·• ∙
          ·  ∙ ∙∙•••∙∙ ∙  ·
"""

WORDMARK = "B I L L I O N"


def _get(path: str, timeout: float = 8.0) -> dict:
    req = urllib.request.Request(f"{BACKEND}{path}")
    if AUTH_TOKEN:
        req.add_header("Authorization", f"Bearer {AUTH_TOKEN}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(path: str, payload: dict, timeout: float = 180.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{BACKEND}{path}", data=data, headers={"Content-Type": "application/json"})
    if AUTH_TOKEN:
        req.add_header("Authorization", f"Bearer {AUTH_TOKEN}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class Spinner:
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, label: str):
        self.label = label
        self._stop = threading.Event()
        self._t: threading.Thread | None = None

    def __enter__(self):
        def run():
            i = 0
            while not self._stop.is_set():
                sys.stdout.write(f"\r  {CYAN}{self.FRAMES[i % len(self.FRAMES)]}{RESET} {self.label}   ")
                sys.stdout.flush()
                i += 1
                time.sleep(0.08)
        self._t = threading.Thread(target=run, daemon=True)
        self._t.start()
        return self

    def done(self, result: str = "", ok: bool = True):
        self._stop.set()
        if self._t:
            self._t.join(timeout=0.5)
        mark = f"{CYAN}✔{RESET}" if ok else f"{RED}✘{RESET}"
        tail = f" {DIM}·{RESET} {result}" if result else ""
        sys.stdout.write(f"\r  {mark} {self.label}{tail}{' ' * 10}\n")
        sys.stdout.flush()

    def clear(self):
        self._stop.set()
        if self._t:
            self._t.join(timeout=0.5)
        sys.stdout.write("\r" + " " * 60 + "\r")
        sys.stdout.flush()

    def __exit__(self, *exc):
        if not self._stop.is_set():
            self.done()
        return False


def type_out(text: str, cps: int = 1100) -> None:
    if os.getenv("BILLION_CLI_INSTANT") == "1" or not sys.stdout.isatty():
        print(text)
        return
    delay = 1.0 / cps
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write("\n")


def _visible_len(s: str) -> int:
    """Length ignoring ANSI escapes."""
    out, i = 0, 0
    while i < len(s):
        if s[i] == "\033":
            while i < len(s) and s[i] != "m":
                i += 1
            i += 1
        else:
            out += 1
            i += 1
    return out


def _pad(s: str, width: int) -> str:
    return s + " " * max(0, width - _visible_len(s))


# ── Boot screen ─────────────────────────────────────────────────────────

def _fetch_boot_data() -> dict:
    """One spinner, several real calls -- everything on the boot screen is
    live backend state, nothing is a hardcoded fake."""
    data: dict = {}
    with Spinner("Establishing uplink") as s:
        try:
            data["health"] = _get("/system/health")
        except Exception as e:
            s.done(f"backend unreachable at {BACKEND} ({e})", ok=False)
            return data
        for key, path in (("llm", "/llm/status"), ("tools", "/tools/catalog"),
                          ("skills", "/skills/library"), ("agents", "/agents/list"),
                          ("memory", "/memory/summary")):
            try:
                data[key] = _get(path)
            except Exception:
                data[key] = None
        s.clear()
    return data


def boot() -> bool:
    cols = shutil.get_terminal_size((110, 30)).columns
    data = _fetch_boot_data()
    if "health" not in data or data.get("health") is None:
        print(f"\n  {RED}✘{RESET} Backend unreachable at {DIM}{BACKEND}{RESET}")
        print(f"  {DIM}Start it first:  cd nancy-billion && docker compose up -d   (or python backend\\main_new.py){RESET}\n")
        return False

    llm = data.get("llm") or {}
    backends = llm.get("backends") or []
    # /llm/status returns [{"name": ..., "model": ...}], but an older or
    # partially-started backend can hand back bare strings. A boot screen is a
    # bad place to raise -- normalise instead of trusting the shape.
    primary = backends[0] if backends else {}
    if isinstance(primary, str):
        primary = {"name": primary}
    elif not isinstance(primary, dict):
        primary = {}
    tools = data.get("tools") or {}
    tool_groups: dict = tools.get("groups") or {}
    total_tools = tools.get("total", 0)
    skills_resp = data.get("skills") or {}
    skills = skills_resp.get("skills") or []
    agents = (data.get("agents") or {}).get("agents") or []
    agents_online = len([a for a in agents if a.get("status") != "offline"])
    mem_total = ((data.get("memory") or {}).get("memory") or {}).get("total_memories", "?")
    cpu = round(((data.get("health") or {}).get("cpu") or {}).get("usage_percent") or 0)

    # ── framed header ──
    title = (f" Billion v{VERSION} ({time.strftime('%Y.%m.%d')}) · backend {BACKEND.replace('http://', '')}"
             f" · {agents_online} agents · load {cpu}% ")
    frame_w = min(cols - 2, 108)
    bar = "─" * max(0, (frame_w - len(title)) // 2)
    inner_w = len(bar) * 2 + len(title)
    print(f"{GOLD}╭{bar}{RESET}{BOLD}{GOLD}{title}{RESET}{GOLD}{bar}╮{RESET}")

    # ── left column: orb + identity ──
    left_lines = [f"{CYAN}{ln}{RESET}" for ln in ORB.strip("\n").splitlines()]
    left_lines.append("")
    left_lines.append(f"   {BOLD}{CYAN}{WORDMARK}{RESET}")
    model_line = f"{primary.get('name', 'no backend')}"
    if primary.get("model"):
        model_line += f" · {primary['model']}"
    left_lines.append(f"   {GOLD}{model_line}{RESET}")
    left_lines.append(f"   {DIM}{mem_total} memories · sovereign core{RESET}")
    left_lines.append(f"   {DIM}{os.getcwd()}{RESET}")
    left_lines.append(f"   {DIM}Session: {SESSION_ID}{RESET}")

    # ── right column: tools + skills ──
    right_lines: list[str] = [f"{GOLD}{BOLD}Available Tools{RESET}"]
    shown_groups = list(tool_groups.items())[:9]
    for group, names in shown_groups:
        joined = ", ".join(names[:4]) + (", …" if len(names) > 4 else "")
        right_lines.append(f"{GOLD}{group}:{RESET} {joined}")
    if len(tool_groups) > len(shown_groups):
        right_lines.append(f"{DIM}(and {len(tool_groups) - len(shown_groups)} more toolsets…){RESET}")
    right_lines.append("")
    right_lines.append(f"{GOLD}{BOLD}Available Skills{RESET}")
    if skills:
        skill_names = [s.get("name", "?") for s in skills]
        for chunk_start in range(0, min(len(skill_names), 12), 4):
            right_lines.append(", ".join(skill_names[chunk_start:chunk_start + 4]))
        if len(skill_names) > 12:
            right_lines.append(f"{DIM}(+{len(skill_names) - 12} more){RESET}")
    else:
        right_lines.append(f"{DIM}none learned yet — Billion distills new skills from real solved tasks{RESET}")

    # ── compose two columns (stack on narrow terminals) ──
    LEFT_W = 42
    print()
    if cols >= 92:
        height = max(len(left_lines), len(right_lines))
        left_lines += [""] * (height - len(left_lines))
        right_lines += [""] * (height - len(right_lines))
        for l, r in zip(left_lines, right_lines):
            print(f" {_pad(l, LEFT_W)} {r}")
    else:
        for l in left_lines:
            print(f" {l}")
        print()
        for r in right_lines:
            print(f" {r}")

    print()
    print(f"  {GOLD}{total_tools} tools · {len(skills)} skills · /help for commands{RESET}")
    print(f"{GOLD}╰{'─' * inner_w}╯{RESET}")
    print()
    return True


# ── commands ────────────────────────────────────────────────────────────

def cmd_status() -> None:
    try:
        health = _get("/system/health")
        llm = _get("/llm/status")
        cpu = round((health.get("cpu") or {}).get("usage_percent") or 0)
        mem = round((health.get("memory") or {}).get("usage_percent") or 0)
        disk = round((health.get("disk") or {}).get("usage_percent") or 0)
        print(f"  {CYAN}neural load{RESET} {cpu}%   {CYAN}memory{RESET} {mem}%   {CYAN}disk{RESET} {disk}%")
        chain = f" {DIM}→{RESET} ".join(b.get("name", "?") for b in llm.get("backends", []))
        print(f"  {CYAN}llm chain{RESET} {chain or '(none)'}")
    except Exception as e:
        print(f"  {RED}status unavailable:{RESET} {e}")


def cmd_agents() -> None:
    try:
        agents = _get("/agents/list").get("agents", [])
        online = [a for a in agents if a.get("status") != "offline"]
        print(f"  {CYAN}{len(online)}{RESET}/{len(agents)} agents online")
        for a in online[:20]:
            mode = a.get("mode")
            badge = f" {GOLD}[{mode}]{RESET}" if mode and mode not in ("production", "real") else ""
            print(f"   {DIM}·{RESET} {a.get('name', a.get('key', '?'))}{badge} {DIM}{a.get('domain', '')}{RESET}")
        if len(online) > 20:
            print(f"   {DIM}… and {len(online) - 20} more{RESET}")
    except Exception as e:
        print(f"  {RED}fleet unavailable:{RESET} {e}")


def cmd_tools() -> None:
    try:
        groups = _get("/tools/catalog").get("groups", {})
        for group, names in groups.items():
            print(f"  {GOLD}{group}:{RESET} {', '.join(names)}")
    except Exception as e:
        print(f"  {RED}tools unavailable:{RESET} {e}")


def cmd_skills() -> None:
    try:
        skills = _get("/skills/library").get("skills", [])
        if not skills:
            print(f"  {DIM}No skills yet — Billion distills them from real solved tasks (with your approval).{RESET}")
        for s in skills:
            uses = s.get("match_count", 0)
            print(f"  {CYAN}{s.get('name', '?')}{RESET} {DIM}· {s.get('description', '')[:70]} · used {uses}×{RESET}")
    except Exception as e:
        print(f"  {RED}skills unavailable:{RESET} {e}")


PROVIDER_SLUGS = ("anthropic", "groq", "opencode", "ollamacloud", "ollama")


def _http_detail(e: urllib.error.HTTPError) -> str:
    try:
        return json.loads(e.read().decode())["detail"]
    except Exception:
        return str(e)


def cmd_model(arg: str) -> None:
    """Hermes-style model selection, three levels deep:

      /model                      the provider chain (● = live primary)
      /model opencode             LIVE numbered list of every model YOUR key
                                  can call on that provider — pick a number
      /model opencode big-pickle  set it directly, no menu
    """
    parts = arg.split(None, 1)
    try:
        # Level 1: provider chain overview
        if not arg:
            backends = _get("/llm/status").get("backends", [])
            print(f"  {GOLD}{BOLD}Model chain{RESET}")
            for i, b in enumerate(backends):
                marker = f"{GOLD}●{RESET}" if i == 0 else f"{DIM}○{RESET}"
                model = f"  {DIM}{b.get('model')}{RESET}" if b.get("model") else ""
                tag = f"  {GOLD}primary{RESET}" if i == 0 else ""
                print(f"  {marker} {b.get('name', '?')}{model}{tag}")
            print(f"\n  {DIM}/model <provider> lists that provider's live models "
                  f"({', '.join(PROVIDER_SLUGS)}){RESET}")
            return

        provider = parts[0].lower()

        # Level 3: direct set
        if len(parts) == 2:
            result = _post("/llm/model", {"backend": provider, "model": parts[1].strip()})
            print(f"  {CYAN}✔{RESET} {result.get('message')}")
            return

        # Level 2: live numbered picker for one provider
        with Spinner(f"Fetching {provider} models (live, your key)") as s:
            data = _get(f"/llm/models?backend={provider}", timeout=20.0)
            s.clear()
        prov = (data.get("providers") or {}).get(provider)
        if not prov:
            print(f"  {RED}✘{RESET} unknown provider '{provider}' — try: {', '.join(PROVIDER_SLUGS)}")
            return
        models = prov.get("models") or []
        current = prov.get("current")
        print(f"  {GOLD}{BOLD}{prov.get('label')}{RESET} {DIM}· {prov.get('total', len(models))} models available to your key{RESET}")
        if not models:
            print(f"  {DIM}none listed — is the API key configured (and the provider reachable)?{RESET}")
            return
        for i, m in enumerate(models, 1):
            here = m == current
            marker = f"{GOLD}●{RESET}" if here else f"{DIM}{i:>3}{RESET}"
            name = f"{BOLD}{m}{RESET}" if here else m
            print(f"  {marker} {name}{f'  {GOLD}current{RESET}' if here else ''}")
        try:
            choice = input(f"  {GOLD}select ›{RESET} ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return
        if not choice:
            return
        if choice.isdigit() and 1 <= int(choice) <= len(models):
            picked = models[int(choice) - 1]
        elif choice in models:
            picked = choice
        else:
            print(f"  {DIM}no selection made{RESET}")
            return
        result = _post("/llm/model", {"backend": provider, "model": picked})
        print(f"  {CYAN}✔{RESET} {result.get('message')}")
    except urllib.error.HTTPError as e:
        print(f"  {RED}✘{RESET} {_http_detail(e)}")
    except Exception as e:
        print(f"  {RED}model command failed:{RESET} {e}")


def cmd_memory(query: str) -> None:
    if not query:
        print(f"  {DIM}/memory <query> — verbatim full-text recall over every past turn{RESET}")
        return
    try:
        from urllib.parse import quote
        results = _get(f"/memory/conversations/search?q={quote(query)}&limit=8").get("results", [])
        if not results:
            print(f"  {DIM}no verbatim matches for '{query}'{RESET}")
        for r in results:
            when = time.strftime("%b %d %H:%M", time.localtime(r.get("ts", 0)))
            print(f"  {DIM}[{when}] {r.get('role')}:{RESET} {r.get('snippet', '')[:100]}")
    except Exception as e:
        print(f"  {RED}memory search failed:{RESET} {e}")


HELP = f"""  {CYAN}/status{RESET}          system health + live LLM chain
  {CYAN}/agents{RESET}          real agent fleet roster (honesty badges included)
  {CYAN}/tools{RESET}           every tool the chat loop can call
  {CYAN}/skills{RESET}          learned skill library + usage counts
  {CYAN}/model{RESET}           the provider chain (● = live primary)
  {CYAN}/model{RESET} <provider> pick from that provider's LIVE model list (numbered)
  {CYAN}/model{RESET} <provider> <model>  set directly, e.g. /model opencode big-pickle
  {CYAN}/memory{RESET} <query>  verbatim recall across every past conversation
  {CYAN}/clear{RESET}           clear the screen
  {CYAN}/quit{RESET}            leave — anything else goes straight to Billion
  {DIM}Same brain as the web UI, voice, and Telegram — tools, skills, memory,
  and one continuous shared conversation. Sensitive actions still ask for
  Telegram approval before executing.{RESET}"""


def repl() -> None:
    wrap_w = min(shutil.get_terminal_size((100, 24)).columns - 4, 100)
    while True:
        try:
            text = input(f"{GOLD}❯{RESET} ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{DIM}Billion standing by. Goodbye, Sir.{RESET}")
            return
        if not text:
            continue
        low = text.lower()
        if low in ("/quit", "/exit", "quit", "exit"):
            print(f"{DIM}Billion standing by. Goodbye, Sir.{RESET}")
            return
        if low == "/help":
            print(HELP)
            continue
        if low == "/clear":
            os.system("cls" if os.name == "nt" else "clear")
            continue
        if low == "/status":
            cmd_status(); continue
        if low == "/agents":
            cmd_agents(); continue
        if low == "/tools":
            cmd_tools(); continue
        if low == "/skills":
            cmd_skills(); continue
        if low.startswith("/model"):
            cmd_model(text[6:].strip()); continue
        if low.startswith("/memory"):
            cmd_memory(text[7:].strip()); continue
        if low.startswith("/"):
            print(f"  {DIM}unknown command — /help lists them{RESET}")
            continue

        with Spinner("Billion is working") as s:
            try:
                result = _post("/chat", {"text": text})
                s.clear()
            except urllib.error.HTTPError as e:
                s.done(f"backend error {e.code}", ok=False)
                continue
            except Exception as e:
                s.done(f"unreachable ({e})", ok=False)
                continue

        reply = (result.get("reply") or result.get("response") or result.get("text") or "").strip()
        if not reply:
            reply = json.dumps(result)[:400]
        sys.stdout.write(f"{CYAN}{BOLD}BILLION ›{RESET} ")
        wrapped = "\n".join(
            textwrap.fill(line, wrap_w, subsequent_indent="  ") if line.strip() else ""
            for line in reply.splitlines()
        )
        type_out(wrapped)
        print()


def main() -> None:
    if not boot():
        sys.exit(1)
    print(f"  {BOLD}{CYAN}BILLION{RESET} {DIM}is listening — same brain as every other surface. Type, or /help.{RESET}\n")
    repl()


if __name__ == "__main__":
    main()
