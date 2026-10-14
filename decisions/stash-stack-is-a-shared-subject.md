# The stash stack is a shared subject

CLAUDE.md says: "Never run `git stash` ... in a shared checkout." It also says: "A
stash entry belongs to no branch. It outlives no session that holds its tag."

The guard read that rule as a rule about the working tree. It is a rule about the
whole stack.

## What was measured

MEASURED 2026-09-19 against `hooks/guard.py` at 2c72892. Three real fixture
repositories carried the probe. One dirty tree with an empty stack. One clean tree
with an empty stack. One clean tree carrying one real stash entry.

| Command | dirty, empty stack | clean, empty stack | clean, one entry |
|---|---|---|---|
| `git stash` | DENY | ALLOW | ALLOW |
| `git stash push -u -m "wip-tag"` | DENY | ALLOW | ALLOW |
| `git reset --hard HEAD` | DENY | ALLOW | ALLOW |
| `git checkout -- f.txt` | DENY | ALLOW | ALLOW |
| `git restore f.txt` | DENY | ALLOW | ALLOW |
| `git stash pop` | ALLOW | ALLOW | ALLOW |
| `git stash apply` | ALLOW | ALLOW | ALLOW |
| `git stash apply stash@{0}` | ALLOW | ALLOW | ALLOW |
| `git stash drop` | ALLOW | ALLOW | DENY |
| `git stash clear` | ALLOW | ALLOW | DENY |
| `git stash branch lane` | DENY | ALLOW | ALLOW |
| `git stash list` | ALLOW | ALLOW | ALLOW |
| `git stash show` | ALLOW | ALLOW | ALLOW |

The table settles two claims from other sessions. First claim: `git stash push -u
-m <tag>` walks past the guard. FALSE. It denies wherever the tree holds work.
Second claim: the guard refuses a drop over a non-empty stack. TRUE. The earlier
report that showed `drop` allowed had measured an EMPTY stack.

The real holes were `pop`, `apply` and `branch`. `pop` and `apply` never matched
the rule at all. `branch` matched but was read against the working tree, so it
passed over a clean tree that carried another session's entry.

## Why the old exemption was wrong

The old exemption for `apply` and `pop` was MEASURED and correct on its own facts.
Git refuses to overwrite a modified file rather than clobber it. The exemption was
wrong about the SUBJECT. The thing at risk in an `apply` or a `pop` is not this
tree. It is the shared stack. A clean tree is exactly the state in which taking
another session's entry leaves no trace.

The dirty-tree precondition stays correct for the arms whose subject IS the
working tree. Those arms are `reset --hard`, `checkout <path>`, `restore`, and the
stash actions that put work onto the stack. The precondition is wrong for the arms
whose subject is the stack.

## The predicate

Not a longer list of action words. The predicate is the act's DIRECTION.

A `git stash` call reads the stack, puts work onto it, or takes an entry off it.
`list` and `show` read. `push`, `save` and a bare `git stash` put work on. Every
other action takes an entry off. A word that is no known action is a pathspec, and
it is read as a push. A known action word that is neither a read nor a push falls on
the stack side. A wrong answer there costs another session its work.

The subject read follows the direction. A call that puts work on is read with
`git status --porcelain`. A call that takes an entry off is read with `git stash
list`. An empty subject still passes, because an empty stack holds nothing to
take and git itself errors there.

Option values are skipped before the action word is read. A value is the next word
after `-m`. It is also the next word after a short cluster that ends in `m`
(`-qm <msg>`). `--message` and `--pathspec-from-file` take one too, by any prefix
git accepts (`--mess <msg>`). A glued value (`-mfoo`, `--message=x`) takes nothing
more. A word after `--` is a push. `export` and `import` are known action words and
keep the stack side. Lane stash-pathspec fixed these reads.

## The conflict this keeps hitting

The harness injects a worktree reminder into every worktree session. In substance it tells the worker to prefer a temporary WIP commit. If the worker
must stash, the reminder asks it to push a tagged entry and capture the SHA. It
then asks the worker to restore with `git stash apply <sha>` rather than `pop`,
and to drop the entry afterwards.

So the harness names `apply` and `drop`, which this rule forbids in a shared
checkout. A worker that obeys the reminder breaks the repo rule. That is why the
incident repeats. The harness reminder is not in this repository and is not
changed here.

What is changed here is the refusal. The stack refusal now points the worker at
the two reads that stay allowed, and at a commit on a branch of the worker's own.
It names no forbidden action. A worker sent here by the reminder reads what to do
instead, which is the only half of the conflict this repository controls.

## Holes, named

- An action word git adds later is read as a push, so the working tree judges it. Over a
  clean tree it passes, even when another session's entry is on the stack. Owner
  ruling pending.
- `git stash create` writes no stack entry and changes no tree, and it falls on
  the stack side. It is refused over a non-empty stack. This is unmeasured
  against real use, and it is a known false refusal.
- An empty stack still passes every arm. A session that pushes an entry between
  the guard's read and the command's run is not covered.
- `git stash -a` and `git stash --all` read as a push over an ignored-only tree, and
  that tree reads as empty. `_tree_subject` in `hooks/guard_shared_tree.py` reads the
  tree without ignored files, so the push passes. Git stashes the ignored files.
  Debt: `stash-all-ignored-tree-passes`.
- `git stash -h` and `git stash --help` are read as a push, so a dirty tree refuses
  them. Git prints help and changes nothing, so the refusal is a false alarm. The read
  is in `stash_action`. Debt: `stash-help-flag-refused-as-push`.
- The comment on the import and export rows in `hooks/test_guard.py` says `import` and
  `export` are not git subcommands. Git 2.55 lists both in `git stash -h`. Comment
  only. Debt: `stash-export-comment-stale`.
