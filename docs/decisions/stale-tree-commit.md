# A commit never runs from a tree its branch moved under

## The ruling

Lane resumed-agent-stale-tree, 2026-11-07, under the parent's lane brief. Orchestrator's call, not an owner grant: the form, the read and the deny.

The guard rule `stale-tree-commit` refuses `git commit` when the index holds the old copy of a file that the branch changed under it. Two steps:

1. Find the old commit X. The branch moved under the checkout when `git rev-parse HEAD` differs from the newest entry of the checkout's own HEAD reflog. Git writes that per-worktree log for every act in the checkout itself, and no entry when another worktree of the same clone moves the shared branch. Then X is that newest entry. Else, when the newest entry's old value differs from the new value of the entry before it, the branch moved under the tree before that entry, and X is that earlier new value. A pull, checkout or `reset --soft` after such a move carries the stale index along, so it does not clear X. Else, when the newest entry is a move that leaves the index alone (a `reset:` entry, or the empty message `update-ref` writes), X is the new value of the entry before it. Else there is no X, and the commit passes.
2. Refuse when X is a strict ancestor of HEAD (the branch moved forward), and the commit would record a copy other than HEAD's for some path that X..HEAD changed, added or deleted. The copy is the index's, or the work tree's for `-a`, `--only` and named paths. That commit would undo the move's change to that path, whole or in part: an edit made on a stale copy still carries the old lines. When X comes from a `reset:` entry alone, only a copy equal to X's counts: the log writes the same message for `--soft` and `--hard`, and `git reset --hard origin/<b>` then an edit is the normal way onto a new tip.

The work-tree copy of a symlink or a submodule is not read, so `-a` and named paths judge only regular files; a stale staged copy of either is still refused. `git commit --dry-run` passes. `git commit -i .` names every path.

The second way to find X covers an agent that moved onto a new tip inside its own tree with `reset --soft` or `update-ref`. Its index still holds the old files. A `reset --soft` back to an older commit, as a squash does, gives an X that is not an ancestor of HEAD, so it passes. With no gap, a commit, pull, merge, rebase or checkout entry gives no X: those acts sync the index, so a revert after them is deliberate. With X found, a pull or `reset --mixed` that did sync the index leaves every copy at HEAD's, so the commit passes.

- Each git call in a chain is judged in its own tree: its `git -C <dir>`, else the cwd after earlier `cd` steps.
- The read needs no fetch. A checkout that never fetched is judged the same.
- Only the newest two entries of the HEAD log are read. A gap further back, behind a `reset --hard`, is not sought: that reset synced the tree, and an unbounded scan costs on every commit.
- A detached HEAD passes: nothing else moves it.
- A checkout with no HEAD reflog passes: there is no evidence either way, and a fresh clone or worktree may start with none.
- A read that fails passes, with the same reason. Git errors on the commit itself in a broken tree.
- Only `commit` is read. Any other command makes no git call for this rule. A commit makes at most five: HEAD, the reflog, the ancestor test, the staged paths, and X's and HEAD's copies of those paths.
- Only the top-level command is read. A commit inside `bash -c` passes (note `stale-tree-inner-shell`).
- An override lifts it.

A push is not refused. A push from the stale tree sends the branch ref, which holds the right commits. The harm starts at the commit. A push from another clone after the branch moved is refused by the remote unless forced, and a forced push is decision `stale-safe-force-push` (a force push needs a lease and `--force-if-includes`).

Remedy the refusal prints: stop, and report that the branch moved under this checkout. The orchestrator starts a fresh agent with the prior report (rule `roles-resume-by-name`). A git recipe is not printed: the measured "detach, then check the branch out again" fails while another worktree holds the branch.

## The incident

On 2026-11-07, 14:32 to 14:42 CST, lane notes-fix-guard-2 resumed agents after another agent's worktree in the same clone pushed to their branch, and told them to move onto it. In four cases the branch moved but the index kept the old copies: 6, 5 and 1 stale staged files, and one commit that landed on the other agent's tip. One agent moved HEAD by a means it did not report; one ran `git checkout -B <b> origin/<b>`. Each was about to commit; one commit was stopped by another guard, and the rest were caught by hand. A commit from such a tree records the reverse of the commits it missed, and the diff looks like a normal edit. Five more lanes hit it the same day. In one, `git pull --ff-only` printed "Already up to date", and `git commit -a` wrote back a stale hooks/test_guard.py, undoing commit 6ca16db54 (an agent's test change on branch role-scope-notes).

Decision `two-worktrees-one-branch` (two worktrees never hold one branch) refuses the checkout forms that let two worktrees share a branch. This rule is the backstop at the commit, for any way the ref moves that the checkout did not make: a commit from another worktree that already holds the branch, `update-ref` from another worktree (git refuses `branch -f` there, but not `update-ref`), or a form that rule does not read.

## Harm it stops

A commit from a stale tree reverts pushed work silently.

Kind: build
Plan: docs/decisions/stale-tree-commit.md#the-ruling (all)
