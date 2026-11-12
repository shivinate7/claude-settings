# A new branch name never holds the word git

## The ruling

Coordinator, 2026-11-12 08:53 CST, in the brief for lane branch-slug-rule-build: the guard rule `branch-slug-no-git` refuses a call that creates a branch whose name holds the word git. The check lives in `hooks/guard_branch_worktree.py`, beside `two_worktrees_form`, and reads push destinations through `guard_push_delete.push_destinations`.

- The word is the lowercase substring `git`, anywhere in the name.
- The forms are `checkout -b`, `-B` and `--orphan`; `switch -c`, `-C`, `--create`, `--force-create` and `--orphan`; `branch <name>`; `worktree add -b` and `-B`. A `push` is one too when its refspec and destination hold the word. The clone must hold no remote-tracking ref for that destination.
- A name that already exists is no creation, so it passes: a local branch for the first four forms, a remote-tracking ref for the push. `checkout -B <name>` of an existing branch is a reset and passes.
- A push with no refspec, a deletion, `--all`, `--mirror`, a tags-only push, a glob and a refspec holding a shell expansion are not read. A read that fails passes.
- The refusal's remedy says to pick a slug without the word. It names no command of the refused form (rule `git-remedy-never-names-target`).

## Harm it stops

Claude Code's own worktree check refuses an agent's git command that names a branch holding the word. A lane that made such a branch could not run its own checkout or push.

## Named limits

- `branch -m|-M|-c|-C <new>` and a `worktree add <path>` with no `-b` (git names the branch from the path) create a name this rule does not read.
- `push origin HEAD` from a local branch that holds the word passes, because the command names no such word.

Kind: process
Home: hooks/guard_branch_worktree.py
