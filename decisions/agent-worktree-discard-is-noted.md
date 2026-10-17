# A discard or remove in a worktree

## The question

The shared-tree rule asks the owner before a discarding git command
runs. The commands are `git reset --hard`, `git checkout -- <path>`,
and `git restore`. The ask fires inside any linked worktree. Is that
ask earned when the worktree is one the harness made for an agent, not
a person? When a command names only files? What does the guard say to a
worktree remove?

Owner rulings: 2026-10-03 (the agent-owned worktree), 2026-10-11 ("Allow per-file", the
untracked link).

## Counted facts

18 shared-tree asks sit in `~/.claude/guard.log` since 2026-09-16 (a lower bound, one machine). The
owner reports the prompt is frequent in agent-heavy repos. There, it
carries nothing to judge. The lane is the agent's own. The agent's
commits already sit on its own branch. They sit in its own reflog too,
before any discard runs.

Counted in guard.log (a lower bound, one machine), this Windows machine's `~/.claude/guard.log`, 30 days to 2026-10-11: 26
`shared-tree` asks, about one a day (decision guard-log-read-weekly, the guard log read by a
note). The ask writes a line there; it is the transcript that holds none.

## Agent-owned worktree

Take a linked worktree. Its resolved path sits under
`<main repo root>/.claude/worktrees/`. Call that an agent-owned
worktree. Inside it, a discard is ALLOWED. It is logged as a note, with
no prompt. A linked worktree anywhere else keeps "ask". The main
checkout keeps "deny". Four things stay unchanged: branch-delete deny,
worktree-remove deny, worktree-prune ask, and every stash deny.

The ask protects a person's own uncommitted work in a worktree they made
by hand. There, a discard has no other copy. So the ask stays for every
worktree outside `.claude/worktrees/`. Inside an agent's own worktree,
the agent's commits are the copy. They sit on the agent's own branch and
in its own reflog. A discard there loses nothing the clone does not
already hold elsewhere.

## Named files in a linked worktree

In a linked worktree, `git checkout <file>` and `git restore <file>` that name only files run
with no ask. The loss is the lane's own change to the files it named, which is what a lane
means when it regenerates a fixture. The allow is an allow-list. `git restore` passes only with the flags `--staged`, `--worktree`,
`-S`, `-W` and `--`. `git checkout` passes with `--` before the paths. Without `--`, it passes
only with one operand that is an existing file. Any other flag or form, or a command that
the tokenizer cannot read, keeps the ask. A whole-tree discard keeps the worktree ask: `reset
--hard`, and a `checkout` or `restore` of `.`, a folder, or a glob. A shared checkout still
denies all of them.

The allow applies only when the whole command acts in one place (`one_place` in
`hooks/guard_shared_tree.py`). One place is no `cd`, `pushd` or `popd` anywhere in the command, and at
most one distinct `git -C` target. Every other shape can hide the shared checkout behind the lane, so it keeps the ask,
and the ask reason names the allowed form: `git -C <lane> restore <file>`. The incident form,
a `cd` into the worktree and then one file, asks. Five review rounds of folder tracking
(`segment_roots`) could not tell the two apart; the gate replaced them (2026-10-11 to 12).

These discard forms join the rule: deny in a shared checkout, ask in a linked worktree.

- `git checkout -f <branch>` and `git checkout --force <branch>`. A forced switch discards local
  changes.
- A bare `git checkout <folder>` with no `--`. Git reads it in path mode.
- `--pathspec-from-file` and each unique prefix that git accepts, such as `--pathspec-from`.
- Each `-C <dir>` in a git call. They chain as git's own chdir does: a relative `-C` joins the
  one before it. The result sets the checkout that the rule judges.
- Every operand of `git restore` counts as a path, before `--` as well as after it.
- A pathspec that holds `$`, a backtick, a brace or a glob counts as a discard of unknown size.
  The guard cannot read what it names.

Found by review, 2026-10-11. Owner: "Do this task here".

## Worktree remove

- An unforced remove: the `subject-unread` note does not fire. The VCS itself refuses a dirty or
  locked tree without `--force` or `-f`, so the note protects nothing. The note stays for a forced
  remove and for every other shared-tree command.
- An untracked entry that is a symlink does not count as work when the guard judges a
  remove. Removing a link deletes only the link. Measured: after
  `git worktree remove --force`, the folder a `node_modules` link pointed to kept its file.
  Incident: feed-build, a worker linked `app/node_modules` to another worktree's packages, and
  the guard refused to remove the scratch tree. Limit: a link whose name git quotes, such as
  one with a space or an accent, still counts as work.

## The rule

hooks/guard.py, rule 1, beside `is_worktree`, holds the check:
`agent_owned_worktree(root)`. It resolves `root` with a real path. It
resolves the primary checkout's `.claude/worktrees/` the same way. The
reads are `primary_checkout` and `path_is_inside`. `agent_worktree_home`
already uses both. This keeps three near misses out: a `..`-spelled
path, a decoy main checkout nested under a look-alike folder, and a
symlink that climbs back out. Each is judged on where it really sits,
never on a "worktrees" segment in its spelling. A hit logs
`record(tool, "noted", "shared-tree", matched)` and allows. A miss keeps
the existing ask. The named-files allow is `names_only_files` and `one_place`
in `hooks/guard_shared_tree.py`.

## Holes, named

Debts: `guard-first-c-reads-wrong-tree` (other rules read the first -C target). `guard-shell-wrap-discard-unread` (a discard inside sh -c, eval or substitution). `stash-allow-any-linked-worktree` (any linked worktree passes the allow).

## Named limits

- A shared checkout reached by `cd`, then `git -C . restore <file>`, gets ask, not deny. An ask reaches the owner. The cost is one prompt.
- The gate fails closed on shape. These keep the ask even when every segment is in the lane.
- Each of these keeps the ask: `cd`, `pushd`, `popd`, `Set-Location`, `sl`, `chdir`, `Push-Location`, `env -C` and `--chdir`.
- Also: two distinct `-C` targets, one lane spelled two ways, and a bare git call beside a `-C` call.
- Also: any `--work-tree`, `--git-dir`, `core.worktree`, `GIT_WORK_TREE`, `GIT_DIR` or `GIT_COMMON_DIR` token.
- Also: `restore --source`, `-p` or `-f`, a glob or `$(…)` pathspec, and a segment the tokenizer cannot read. The remedy names the `-C` form.
- Setting `GIT_DIR`, `GIT_WORK_TREE` or `GIT_INDEX_FILE` is denied, not asked. See `git-env-set-denied` (the record that denies setting git env vars).

## Lint

This record changes the gate's verdict for a real class of commands.
A reviewer reads this diff.

Kind: process
Home: hooks/guard_shared_tree.py
