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

The stack refusal points the agent at the two reads that stay allowed and at a commit on a branch
of the agent's own. It names no forbidden action. Reason: the harness's worktree reminder names
`apply` and `drop`, which this rule forbids in a shared checkout. That reminder is not in this
repository and is not changed here.

`git stash -h` and `git stash --help` pass over a dirty shared tree: they print usage and read no
stack and no tree. The allow holds only when the help flag is the sole argument after `stash`.
`git stash -h list`, `stash push -h`, `stash -u -h` and every other form keep their verdict.

Kind: process
Home: hooks/guard_shared_tree.py
