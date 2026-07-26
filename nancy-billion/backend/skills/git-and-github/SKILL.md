---
name: git-and-github
description: Read repo state and make git/GitHub changes safely via the execute_command tool.
trigger_keywords:
  - git
  - github
  - repo
  - repository
  - commit
  - push
  - pull request
  - pr
  - branch
  - clone
---

You have a real `execute_command` tool that runs actual shell commands on the
user's machine, including `git` and the `gh` CLI. Use it directly instead of
describing what you would do.

## Reading state (runs immediately, no approval needed)

- `git status`, `git diff`, `git log --oneline -10`, `git branch -a`
- `gh repo view`, `gh issue list`, `gh pr list`, `gh pr view <number>`

Always check `git status` and `git diff` before proposing or making any
change, so your summary reflects what's actually in the working tree, not an
assumption.

## Making changes (requires the user's approval -- this is enforced by the
tool itself, not just a convention: `execute_command` will pause and send a
yes/no prompt to the user's phone before running anything not on the
read-only allowlist)

1. Stage precisely: `git add <specific files>` -- never `git add -A` or
   `git add .` unless the user explicitly asked for everything, since that
   can sweep up unrelated or sensitive files.
2. Commit with a message that explains *why*, not just *what* changed.
3. Push only the current branch (`git push origin <branch>`), never force
   unless the user explicitly asked for a force push, and warn them first if
   the target is `main`/`master`.
4. For a PR: `gh pr create --title "..." --body "..."`, keeping the title
   under ~70 characters and putting detail in the body.

## Safety notes

- Never run `git reset --hard`, `git clean -fd`, or `git checkout -- .`
  without first running `git status` and getting explicit confirmation --
  these discard uncommitted work irreversibly.
- If `git status` shows unexpected changes (files you didn't just touch),
  stop and tell the user before doing anything else -- don't assume it's safe
  to include them.
- Never commit files that look like they contain secrets (`.env`, files with
  "credential"/"secret"/"key" in the name) without explicitly flagging it to
  the user first.
