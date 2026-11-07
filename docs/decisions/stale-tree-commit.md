# A commit never runs from a tree its branch moved under

## The ruling

Lane resumed-agent-stale-tree, 2026-11-07, under the parent's lane brief. Orchestrator's call, not an owner grant: the form, the read and the deny.

The guard rule `stale-tree-commit` refuses `git commit` in a checkout whose branch moved under it. The branch moved under it when `git rev-parse HEAD` differs from the newest entry of that checkout's own HEAD reflog (`git reflog -1 --format=%H HEAD`). Git writes that per-worktree log for every act in the checkout itself: commit, amend, pull, merge, rebase, reset, checkout, and `update-ref` on the checked-out branch. It writes no entry when another worktree of the same clone moves the shared branch ref. So a mismatch means the files and index sit at the old commit while the branch sits at a new one.

- Each git call in a chain is judged in its own tree: its `git -C <dir>`, else the cwd after earlier `cd` steps.
- The read needs no fetch. A checkout that never fetched is judged the same.
- A detached HEAD passes: nothing else moves it.
- A checkout with no HEAD reflog passes: there is no evidence either way, and a fresh clone or worktree may start with none.
- A read that fails passes, with the same reason. Git errors on the commit itself in a broken tree.
- Only `commit` is read. Any other command makes no git call for this rule. A commit makes at most two.
- An override lifts it.

A push is not refused. A push from the stale tree sends the branch ref, which holds the right commits. The harm starts at the commit. A push from another clone after the branch moved is refused by the remote unless forced, and a forced push is decision `stale-safe-force-push` (a force push needs a lease and `--force-if-includes`).

Remedy the refusal prints: stop, and report that the branch moved under this checkout. The orchestrator starts a fresh agent with the prior report (rule `roles-resume-by-name`). A git recipe is not printed: the measured "detach, then check the branch out again" fails while another worktree holds the branch.

## The incident

On 2026-11-07, lane notes-fix-guard-2 saw three resumed agents keep a stale index and tree after their branch moved under them. A commit from such a tree records the reverse of the commits it missed, and the diff looks like a normal edit.

Decision `two-worktrees-one-branch` (two worktrees never hold one branch) refuses the checkout forms that let two worktrees share a branch. This rule is the backstop at the commit, for any way the ref moves that the checkout did not make: a commit from another worktree that already holds the branch, `update-ref` from another worktree (git refuses `branch -f` there, but not `update-ref`), or a form that rule does not read.

## Harm it stops

A commit from a stale tree reverts pushed work silently.

Kind: build
Plan: docs/decisions/stale-tree-commit.md#the-ruling (all)
