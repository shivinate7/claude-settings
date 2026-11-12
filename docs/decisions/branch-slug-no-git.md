# A new branch name never holds the word git

## The ruling

Coordinator pick a, 2026-11-07 14:51 CST: a new branch slug never holds the word git, applied where branch names are read. Coordinator yes, 2026-11-12 07:21 CST: step back to ready. The guard rule `branch-slug-no-git` refuses a call that creates a branch whose name holds the word git. The guard rule lives in `hooks/guard_branch_worktree.py`, beside `two_worktrees_form`, and reads push destinations through `guard_push_delete.push_destinations`.

- The word is the lowercase substring `git`, anywhere in the name.
- The forms are `checkout -b`, `-B` and `--orphan`; `switch -c`, `-C`, `--create`, `--force-create` and `--orphan`; `branch <name>`; `worktree add -b` and `-B`. A `push` is one too when its refspec and destination hold the word. The clone must hold no remote-tracking ref and no local branch for that destination (lane pick below).
- A name that already exists is no creation, so it passes: a local branch for the first four forms, a remote-tracking ref or a local branch for the push. `checkout -B <name>` of an existing branch is a reset and passes.
- A push with no refspec, a deletion, `--all`, `--mirror`, a tags-only push, a glob and a refspec holding a shell expansion are not read. A read that fails passes.
- The refusal's remedy says to pick a slug without the word. A push refusal says to fetch origin and retry instead (lane pick below). Neither names a command of the refused form (rule `git-remedy-never-names-target`).
- Lane pick, 09:36 CST Nov 12, under the coordinator's rule that a reversible choice that keeps main's behaviour is taken, not asked:
  - A branch made from `origin/<same name>` passes.
  - A push passes when its destination exists as a local branch or as a remote-tracking ref.
  - A push to a git-named destination that exists neither locally nor as a remote-tracking ref is refused. Its reason says to fetch origin and retry.

## Harm it stops

Claude Code's own worktree check refuses an agent's git command that names a branch holding the word. A lane that made such a branch could not run its own checkout or push.

## Named limits

- `branch -m|-M|-c|-C <new>` and a `worktree add <path>` with no `-b` (git names the branch from the path) create a name this rule does not read.
- `push origin HEAD` from a local branch that holds the word passes, because the command names no such word.
- A git call inside `bash -c "..."`, such as `bash -c "git checkout -b x"`, is not read.
- A push whose name holds `$` is not read.

Kind: process
Home: hooks/guard_branch_worktree.py
