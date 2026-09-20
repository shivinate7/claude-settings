# A stash push is clone-wide, not lane-wide

CLAUDE.md says: "Set work aside with a commit on your own branch, never a stash." It
also says: "A stash entry belongs to no branch. It outlives no session that holds its
tag."

The guard read `push` (and `save`, and a bare `git stash`) as a working-tree act. It
gave that act the same worktree "ask" it gives `reset --hard`, `checkout <path>` and
`restore`. That ask is earned by TREE_ASK_REASON's own argument: "This checkout is a
worktree, so the loss is limited to this lane." The argument is false for a push.

## What was measured

MEASURED 2026-09-19, `hooks/guard.py` at the commit before this change. A linked
worktree (`GITWT`) of a shared checkout (`GITMAIN`), both carrying real uncommitted
work.

| Command | shared checkout | linked worktree |
|---|---|---|
| `git stash push -u -m lane` | DENY | ASK |
| `git stash` (bare) | DENY | ASK |
| `git stash save lane` | DENY | ASK |
| `git reset --hard` | DENY | ASK |
| `git restore f.txt` | DENY | ASK |
| `git checkout -- f.txt` | DENY | ASK |

Same command, same guard, same "this lane only" grant on both rows. That is the
defect: `refs/stash` is not lane-scoped the way the working tree is.

`git rev-parse --git-path refs/stash` from inside the worktree answers
`<repo>/.git/refs/stash`, not the worktree's own `.git/worktrees/<name>/...` path. The
test suite already carries this fact, next to `SUBJSTASHWT`: "`refs/stash` lives in
the common git directory, so the worktree sees the same one-entry stack." That
comment was written for the TAKE arm (`pop`, `drop`, `clear`, `apply`, `branch`).
That arm already denies everywhere. The same fact holds for the PUT arm. The guard
had not applied it there.

## Why the worktree exemption was wrong for this arm

The exemption is right when the subject is the WORKTREE's own tree. `reset --hard`
throws away that tree's own uncommitted changes. `restore` and `checkout <path>`
overwrite that tree's own paths. A lane's tree is that lane's own. A discard there
loses only that lane's own work, so the ask is a real, lane-scoped grant.

A stash push does not write to the worktree's own tree. It writes an entry to
`refs/stash`. That ref is the ONE the primary checkout and every other linked
worktree already read and write. A push from a worktree competes for the same
one-entry-wide slot a `pop` or a `drop` elsewhere in the clone would consume. The
"this lane only" grant the ask hands out is a grant over a subject the ask has no
authority over.

Second reason, measured this session: an "ask" has no human behind it in a fanned-out
worker. A worker briefed to "set work aside" reads the ask as permission. The worker
then stashes, because nothing in the prompt stops to ask a person. The rule text
("never a stash") was already the answer. The guard's own ask contradicted it, for
exactly the arm most likely to run unattended.

## The fix

`push`, `save` and a bare `git stash` now deny in every tree, worktree or not, the
same way the TAKE arm already denies in every tree. The read that decides whether the
call would discard anything is unchanged. That read, `stash_subject`, checks the
WORKING TREE for this arm, so a push over a clean tree still passes: it takes
nothing. Once the tree is dirty enough to be taken, the call denies. The
`is_worktree` check no longer runs for this arm.

`reset --hard`, `checkout <path>` and `restore` keep their worktree ask exactly as
before. Their subject is still the lane's own tree. TREE_ASK_REASON's argument still
holds for them.

## The predicate, updated

`stash_takes_the_stack` already named the TAKE arm's subject as clone-wide. This
change gives the PUT arm the same clone-wide reading. It denies the PUT arm before
the worktree check runs at all, rather than widening `stash_takes_the_stack` itself.
The three actions stay grouped as PUT versus TAKE versus READ. Only the tree that
each judgment consults, and the tree the deny now covers, changes for PUT.

## Holes, named

- `git stash create` writes no ref by itself. It returns a commit with no ref
  pointing at it, unless piped into `git stash store`. It is not `push` or `save`,
  and it falls outside `STASH_TREE_ACTIONS`, so `stash_takes_the_stack` reads it as a
  TAKE. It denies over a non-empty stack. This is unmeasured against real use of
  `create` piped into `store`. It is the same known false-refusal shape the earlier
  decision (stash-stack-is-a-shared-subject) already named for `create`.
- The harness's own worktree reminder still tells a worker to push a tagged entry.
  This guard change makes that path deny outright rather than ask. The reminder text
  is not in this repository and is not changed here.
- An empty tree still passes a push in every tree. A session that dirties the tree
  between the guard's read and the command's run is not covered. This is the same gap
  the earlier decision named for the TAKE arm.
