# A discard or remove in a worktree

## The ruling

Owner rulings: 2026-10-03 (the agent-owned worktree), 2026-10-11 ("Allow per-file", the untracked
link), 2026-10-17 11:40 CDT (the per-file allow outside `.claude/worktrees/` stands).

The shared-tree rule refuses a discarding git command in the shared checkout. In a hand-made
worktree it asks for `git reset --hard`. It asks for `git checkout -- <path>` or `git restore` too,
except a named file. The shared checkout refuses named files.

### Agent-owned worktree

Take a linked worktree whose real path sits under `<main repo root>/.claude/worktrees/`, never a
"worktrees" segment in its spelling (`agent_owned_worktree(root)` in `hooks/guard.py`). Call that an
agent-owned worktree. Inside it, a discard is ALLOWED. It is logged as a note, with no prompt. A linked
worktree anywhere else keeps "ask", except a named-file discard (see Named files). The main checkout
keeps "deny". Four things stay unchanged: branch-delete refusal, worktree-remove refusal, worktree-prune ask,
and every stash refusal.

Reason: the ask protects a person's own uncommitted work in a worktree they made by hand. The owner makes
no worktree by hand (owner, 2026-10-17 11:40 CDT). Claude sessions make them, or the desktop app's
worktree checkbox does. So the per-file allow outside `.claude/worktrees/` stands. Whole-tree discards
there keep the ask. Inside an agent's own worktree, the agent's commits are the copy, on its own branch
and in its own reflog.

### Named files in a linked worktree

In a linked worktree, `git checkout <file>` and `git restore <file>` that name only files run with no
ask. Reason: the loss is the lane's own change to the files it named, which is what a lane means when it
regenerates a fixture. The allow is an allow-list (`names_only_files` and `one_place` in
`hooks/guard_shared_tree.py`). Any other flag or form keeps the ask, as does a command the tokenizer
cannot read. A whole-tree discard (`reset --hard`, or a `checkout` or `restore` of `.`, a folder or a
glob) keeps the worktree ask. A shared checkout still refuses all of them.

The allow applies only when the whole command acts in one place (`one_place`). The command has no
directory change and at most one distinct `git -C` target. Every other shape can hide the shared
checkout behind the lane, so it keeps the ask. The ask reason names the allowed form:
`git -C <lane> restore <file>`. The incident form, a `cd` into the worktree and then one file, asks.
Setting `GIT_DIR`, `GIT_WORK_TREE` or `GIT_INDEX_FILE` is refused, not asked (`git-env-set-refused`,
setting git env vars is refused).

These discard forms join the rule: refused in a shared checkout, ask in a linked worktree.

- `git checkout -f <branch>` and `git checkout --force <branch>`. A forced switch discards local
  changes.
- A bare `git checkout <folder>` with no `--`. Git reads it in path mode.
- A bare `git checkout <file>` with no `--`, when the file is tracked, has an uncommitted change, and
  no branch or other revision has its name. The guard reads git state (`lone_operand_is_dirty_file`),
  not the file extension, so `Makefile` and `tools/runner` count as `a.json` does. It reads the name
  only to skip an empty name and one that starts with `-` or `:`. A name that is both a branch and a
  file stays a branch, as git reads it. A clean file and a branch keep their answers. In a hand-made
  worktree the named-file allow stays (`names_only_files` and `one_place`, "Named files in a linked
  worktree" above), and the call asks only when it holds a `cd`. Incident: 2026-11-08 03:37
  CST, with coordinator rulings at 04:38 and 05:16 CST. An agent-owned worktree keeps its named-file
  allow.
  - Cost: 0 git starts when no file of that name exists, 1 when it is a revision, 2 otherwise.
  - A staged-only change is refused, the same as main's `git checkout -- <path>`, even though git
    keeps the staged change.
  - An unreadable git answer allows and logs `subject-unread`.
- `--pathspec-from-file` and each unique prefix that git accepts, such as `--pathspec-from`.
- Each `-C <dir>` in a git call. They chain as git's own chdir does. The result sets the checkout that
  the rule judges.
- Every operand of `git restore` counts as a path, before `--` as well as after it.
- A pathspec that holds `$`, a backtick, a brace or a glob counts as a discard of unknown size.

### Worktree remove

- An unforced remove: the `subject-unread` note does not fire. The VCS itself refuses a dirty or locked
  tree without `--force` or `-f`, so the note protects nothing. The note stays for a forced remove and
  for every other shared-tree command.
- An untracked entry that is a symlink does not count as work when the guard judges a remove. Removing
  a link deletes only the link.

## Path reset and work-tree discards

Verdicts by tree: shared | hand-made | agent-owned. Pinned by the path reset ruling block in
`hooks/test_guard.py` (title: THE PATH RESET AND DISCARD RULING). A `deny | ask | allow, noted` row
holds only over uncommitted work. A clean tree allows, as the rows
`subject: a hard reset in a clean tree takes nothing` and
`subject: restoring the whole clean tree changes nothing` show.

- `git reset [-q] [HEAD] [--] [<path>]`, no discard flag: allow | allow | allow. It only unstages and
  keeps the work tree. In the shared checkout it can drop another agent's staged choice. The allow
  stays. The coordinator (2026-11-08 07:50 CST) asked for an explicit judgement of this case.
  - Unstage caveat: an unstage never touches the work tree. If the work tree still holds the staged
    lines, nothing is lost. If the work tree changed a line after it was staged, the staged version
    is in no ref, index or file after the unstage. It survives only as an unreachable blob until gc.
    The allow stays. Measured: after add, edit and unstage, the work tree keeps the newer
    bytes, and `git fsck --lost-found` recovers the staged bytes. Asking on every unstage would be a
    false alarm, since any agent's `git add` or `git commit` already changes the shared index. The
    `MM` state also comes from add-then-edit.
- `git restore --staged <path>` and `git restore --staged .`: allow | allow | allow. Each is an
  unstage, so the caveat above applies.
- `git restore -- <path>`: deny | allow (named-file allow) | allow, noted.
- `git reset --hard|--merge|--keep` with a path (`… -- <path>`): deny | ask | allow, noted. Git refuses
  this form itself ("Cannot do <mode> reset with paths"), so these pinned verdicts cost nothing and
  guard nothing.
- `git checkout -- .`, `git checkout -q -- .`, `git checkout HEAD -- .` and `git restore .`: deny |
  ask | allow, noted. The agent-owned allow is the owner ruling of 2026-10-03, re-affirmed 2026-10-17
  11:40 CDT. Second sighting: lane `findings-ride-in-lane`, 2026-11-08. A builder discarded its own
  edit in its own worktree. Nothing was lost, and the ruling allows it.

Kind: process
Home: hooks/guard_shared_tree.py
