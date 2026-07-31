---
name: python-kernel
description: Real, persistent IPython kernel (run_python_kernel) -- variables and imports survive between calls, unlike execute_command's fresh subprocess each time.
trigger_keywords:
  - run this python
  - run python
  - python kernel
  - jupyter
  - execute this code
---

Nancy has a real, stateful Python execution tool (`jupyter_tools.py`), a
genuine IPython kernel via `jupyter_client`/`ipykernel` -- not a subprocess
that dies after one command.

- `run_python_kernel(code)`: variables, imports, and function/class
  definitions from EARLIER calls in this same conversation are still there.
  Real stdout, the real repr of the last expression (exactly like a Jupyter
  cell), and a real image if the code produced a matplotlib/PIL plot.
- `restart_python_kernel()`: clears all kernel state for a genuinely fresh start.

Use this instead of `execute_command python -c ...` whenever state carrying
over between steps is useful (building up a dataframe across several turns,
iterating on a plot). Use `execute_command` instead for shell commands or
one-shot scripts where a fresh process each time is the correct behavior.

The kernel is a real, shared, single instance for this backend -- a crash
or hang in the user's code affects it until restarted, so treat
`restart_python_kernel` as the real recovery action it is, not a formality.
