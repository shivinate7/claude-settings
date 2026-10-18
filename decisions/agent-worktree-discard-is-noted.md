# A discard or remove in a worktree

## The ruling

Owner rulings: 2026-10-03 (the agent-owned worktree), 2026-10-11 ("Allow per-file", the untracked
link), 2026-10-17 11:40 CDT (the per-file allow outside `.claude/worktrees/` stands).

The shared-tree rule asks before a discarding git command runs: `git reset --hard`,
`git checkout -- <path>`, `git restore`.

### Agent-owned worktree

Take a linked worktree. Its resolved path sits under `<main repo root>/.claude/worktrees/`. Call that an
agent-owned worktree. Inside it, a discard is ALLOWED. It is logged as a note, with no prompt. A linked
worktree anywhere else keeps "ask", except a named-file discard (see Named files). The main checkout
keeps "deny". Four things stay unchanged: branch-delete deny, worktree-remove deny, worktree-prune ask,
and every stash deny.

Reason: the ask protects a person's own uncommitted work in a worktree they made by hand. The owner makes
no worktree by hand (owner, 2026-10-17 11:40 CDT). Claude sessions make them, or the desktop app's
worktree checkbox does. So the per-file allow outside `.claude/worktrees/` stands. Whole-tree discards
there keep the ask. Inside an agent's own worktree, the agent's commits are the copy, on its own branch
and in its own reflog.

The guard judges where the worktree really sits, never a "worktrees" segment in its spelling. It
resolves the root and the primary checkout's `.claude/worktrees/` with a real path. A hit logs
`record(tool, "noted", "shared-tree", matched)` and allows. A miss keeps the ask.
`agent_owned_worktree(root)` in `hooks/guard.py` (rule 1) holds the check.

### Named files in a linked worktree

In a linked worktree, `git checkout <file>` and `git restore <file>` that name only files run with no
ask. Reason: the loss is the lane's own change to the files it named, which is what a lane means when it
regenerates a fixture. The allow is an allow-list, `names_only_files` and `one_place` in
`hooks/guard_shared_tree.py`.

- `git restore` passes only with the flags `--staged`, `--worktree`, `-S`, `-W` and `--`.
- `git checkout` passes with `--` before the paths. Without `--`, it passes only with one operand that
  is an existing file.
- Any other flag or form, or a command that the tokenizer cannot read, keeps the ask.
- A whole-tree discard keeps the worktree ask: `reset --hard`, and a `checkout` or `restore` of `.`, a
  folder, or a glob. A shared checkout still denies all of them.

The allow applies only when the whole command acts in one place (`one_place`). One place is no `cd`,
`pushd` or `popd` anywhere in the command, and at most one distinct `git -C` target. Every other shape
can hide the shared checkout behind the lane, so it keeps the ask. The ask reason names the allowed form:
`git -C <lane> restore <file>`. The incident form, a `cd` into the worktree and then one file, asks.

These discard forms join the rule: deny in a shared checkout, ask in a linked worktree.

- `git checkout -f <branch>` and `git checkout --force <branch>`. A forced switch discards local
  changes.
- A bare `git checkout <folder>` with no `--`. Git reads it in path mode.
- `--pathspec-from-file` and each unique prefix that git accepts, such as `--pathspec-from`.
- Each `-C <dir>` in a git call. They chain as git's own chdir does. The result sets the checkout that
  the rule judges.
- Every operand of `git restore` counts as a path, before `--` as well as after it.
- A pathspec that holds `$`, a backtick, a brace or a glob counts as a discard of unknown size.

The gate fails closed on shape. These keep the ask even when every segment is in the lane:

- A directory change: `cd`, `pushd`, `popd`, `Set-Location`, `env -C`, `--chdir` and the like.
- Two distinct `-C` targets, or a bare git call beside a `-C` call.
- Any `--work-tree`, `--git-dir`, `core.worktree`, `GIT_WORK_TREE`, `GIT_DIR` or `GIT_COMMON_DIR` token.
- `restore --source`, `-p` or `-f`, and a segment the tokenizer cannot read.

The remedy names the `-C` form. A shared checkout reached by `cd`, then `git -C . restore <file>`, gets
ask, not deny. Setting `GIT_DIR`, `GIT_WORK_TREE` or `GIT_INDEX_FILE` is denied, not asked
(`git-env-set-denied`, setting git env vars is denied).

### Worktree remove

- An unforced remove: the `subject-unread` note does not fire. The VCS itself refuses a dirty or locked
  tree without `--force` or `-f`, so the note protects nothing. The note stays for a forced remove and
  for every other shared-tree command.
- An untracked entry that is a symlink does not count as work when the guard judges a remove. Removing
  a link deletes only the link.

Kind: process
Home: hooks/guard_shared_tree.py
