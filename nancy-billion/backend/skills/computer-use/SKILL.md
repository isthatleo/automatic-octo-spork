---
name: computer-use
description: Real local screen control (screenshot, mouse, keyboard) via pyautogui -- the highest-risk tool in this system, every action gated by live approval.
trigger_keywords:
  - screenshot
  - click the screen
  - move the mouse
  - control my computer
  - control my screen
  - press a key
  - type this
---

Nancy has real local computer-use tools (`computer_use_tool.py`): a genuine
screenshot (`take_screenshot`, which Claude can actually SEE via a real
vision-capable tool result, not just a text description), real screen
resolution (`get_screen_size`), and real mouse/keyboard control
(`click_screen`, `move_mouse`, `type_text`, `press_key`, `scroll_screen`).

This is the highest-risk capability in the system -- unlike a terminal
command or a file write, mouse/keyboard control can do anything a human at
this machine could do. There is no safe/unapproved subset: every single
action (click, move, type, keypress, scroll) requires a real Telegram
yes/no approval before it executes, with no exceptions. Screenshot and
screen-size are read-only and don't need approval.

## Answering

- Take a screenshot first when you need to know what's actually on screen
  before deciding where to click -- never guess coordinates from a
  description alone.
- Never imply an action already happened before the approval response comes
  back -- if approval is denied or times out, say so plainly.
- Because pyautogui's fail-safe is enabled, moving the mouse to a screen
  corner (yours, physically) aborts whatever's in progress -- mention this
  if the user seems unsure how to interrupt something.
