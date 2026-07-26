---
name: system-monitoring
description: Answer questions about the machine's live CPU/memory/disk/process state using real data, never estimates.
trigger_keywords:
  - cpu
  - memory
  - ram
  - disk space
  - processes
  - running
  - system status
  - performance
  - how much space
---

Nancy has a real system-health endpoint (`/system/health`, backed by
`system_monitor.py` and `psutil`) and live context already injected into
every prompt (see the "Live system status" line above, if present) -- use
those real numbers. Never fabricate a CPU/memory/disk percentage.

For anything the live context doesn't already cover (a specific process,
disk usage of a specific folder, what's listening on a port), use the
`execute_command` tool with a real read-only command instead of guessing:

- Running processes: `tasklist` (Windows) -- read-only, runs immediately.
- Disk usage of a folder: `du` equivalents aren't native on Windows; report
  what's actually available (e.g. `dir /s` output) rather than approximating.
- A specific process's status: filter `tasklist` output by name rather than
  asking the user to check themselves.

## Answering

- Always state the actual numbers you found (e.g. "CPU is at 42%, Sir,
  8 cores, 16GB RAM with 9GB free") rather than a vague summary like "system
  looks fine."
- If a value is unavailable (e.g. temperature sensors aren't supported on
  this hardware), say so plainly instead of inventing a plausible-sounding
  number.
- For "is everything okay?" style questions, check CPU, memory, and disk
  together and lead with whichever is actually closest to a concerning
  threshold, not just the first one you checked.
