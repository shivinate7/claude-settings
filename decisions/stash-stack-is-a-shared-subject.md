# The stash stack is a shared subject

## The ruling

CLAUDE.md says: "A stash entry belongs to no branch." The guard reads `git stash` against the
whole stack, not only the working tree. Reason: a clean tree is exactly the state in which taking
another session's entry leaves no trace.

The predicate is the act's direction:

- `list` and `show` read the stack. They pass.
- `push`, `save` and a bare `git stash` put work on. The subject is the working tree, read with
  `git status --porcelain`.
- Every other action takes an entry off (`pop`, `apply`, `drop`, `clear`, `branch`, `export`,
  `import`). The subject is the stack, read with `git stash list`. A wrong answer here costs
  another session its work.
- An empty subject passes, because an empty stack holds nothing to take and git itself errors there.
- A word that is no known action is a pathspec, read as a push. A known action that is neither a
  read nor a push falls on the stack side.
- Option values are skipped before the action word is read: the next word after `-m` or a short
  cluster that ends in `m`, and the value of `--message` and `--pathspec-from-file` by any prefix
  git accepts. A glued value takes nothing more. A word after `--` is a push.

The stack refusal points the worker at the two reads that stay allowed and at a commit on a branch
of the worker's own. It names no forbidden action. Reason: the harness's worktree reminder names
`apply` and `drop`, which this rule forbids in a shared checkout. That reminder is not in this
repository and is not changed here.

The rule lives in `hooks/guard_shared_tree.py`. The shared-tree family of `hooks/test_guard.py` pins it.

## Build plan

### windows

The gates-windows-guard job runs the guard fixture suite, as the Windows slice on a pull
request and in full on main.

### macos

The gates-macos job runs the guard fixture suite in full.

Kind: build
Plan: decisions/stash-stack-is-a-shared-subject.md#windows (windows)
Plan: decisions/stash-stack-is-a-shared-subject.md#macos (macos)
