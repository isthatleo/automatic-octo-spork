---
name: file-organization
description: Inspect and reorganize files/folders on the user's machine using the real file and terminal tools.
trigger_keywords:
  - organize
  - clean up
  - tidy
  - sort files
  - folder
  - directory
  - downloads
  - desktop
---

You have real `list_directory`, `read_file`, `write_file`, `delete_file`, and
`move_file` tools, plus `execute_command` for anything they don't cover
(e.g. bulk operations, finding files by pattern). There is no folder
sandbox -- any path the backend process can reach is fair game, which means
you must be careful, not that you should hold back.

## Before moving or deleting anything

1. `list_directory` the target folder first and actually look at what's in
   it -- don't guess based on the folder name alone.
2. Explain your plan (what moves where, what gets deleted) before acting,
   unless the user's request was already fully specific.
3. `write_file`, `delete_file`, and `move_file` each require the user's
   explicit approval (enforced by the tool itself) -- this is a real safety
   check, not a formality, so don't try to work around it by shelling out to
   `del`/`rm` via `execute_command` instead.

## Doing the work

- Prefer `move_file` over delete+recreate when reorganizing -- it's one
  reversible operation instead of two, and preserves the file's content
  exactly.
- For "clean up my Downloads" style requests, group by a sensible axis
  (file type, date, or project) and say which axis you used -- don't
  silently pick one without mentioning it.
- If a destination folder doesn't exist yet, say so and either create it
  (with approval) or ask which existing folder to use instead.

## Safety notes

- Never delete something you haven't listed/read first.
- If a filename suggests it might be a backup, config, or system file (look
  for `.bak`, `.old`, dotfiles, anything under a `node_modules`/`.git`
  directory), flag it and ask before touching it rather than assuming it's
  safe to move or delete.
