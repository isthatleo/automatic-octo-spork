---
name: scheduled-jobs
description: Set up real recurring/scheduled work via the cron job store -- never a "sure, I'll remind you" reply that doesn't actually get persisted anywhere.
trigger_keywords:
  - remind me
  - every day
  - every morning
  - every hour
  - schedule
  - cron
  - recurring
  - daily
  - weekly
  - at 9am
  - automate
---

Nancy has a real, persisted scheduled-job system (`cron_store.py` +
`_cron_execution_loop`, checked every 30s) backing the Cron Jobs page --
"remind me every morning" must become an actual job, not a reply that sounds
like a promise and forgets itself the moment the conversation ends.

Create jobs via `POST /cron/jobs` with:
- `name`, `description`
- either a simple daily `hour`/`minute`, or a real `cron_expression`
  (standard 5-field cron syntax, e.g. `*/15 * * * *` for every 15 minutes,
  `0 9 * * 1-5` for 9am weekdays) when the user's ask is more specific than
  "once a day"
- `action_type`, one of:
  - `telegram_message` -- payload `{"text": str}`
  - `agent_task` -- payload `{"agent_key": str, "task_type": str, "payload": dict}`
  - `run_skill` -- payload `{"skill_name": str, "context": str}`, runs another
    skill's real procedure on schedule (with tool access)
  - `terminal_command` -- payload `{"command": str, "cwd": str | None}`, gated
    by the same safe-command allowlist/Telegram-approval split as any other
    shell command

## Answering

- After creating a job, confirm the real next-run time (`next_run()` on the
  created job), not a vague "okay, I'll remind you."
- List existing jobs via `GET /cron/jobs` before claiming none exist.
- A destructive `terminal_command` job still needs approval at run time even
  though it was scheduled in advance -- don't imply otherwise to the user.
