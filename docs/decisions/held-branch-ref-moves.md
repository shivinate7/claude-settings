Merge after: #1583

# A ref move never touches a branch another worktree holds

## The ruling

The guard rule `two-worktrees-one-branch` also refuses `update-ref` and `symbolic-ref HEAD` on a branch another worktree holds (decision two-worktrees-one-branch, two worktrees never hold one branch). Lane push-branch-held-elsewhere, 2026-11-08, builder's call under the brief, not an owner grant. These are the two git calls that write a branch ref with no worktree check:

- `git update-ref [-m <msg>] [--no-deref] refs/heads/<branch> <value>`, and `git update-ref -d refs/heads/<branch>`. `-m` takes a value, so the branch is the first word that is not an option or an option's value.
- `git symbolic-ref HEAD refs/heads/<branch>`. It points the running tree's HEAD at the branch, so two trees then hold one branch.

Both are refused when another worktree of the clone holds `<branch>`. The family rules are the same as the parent decision's, with one change. The worktree list is read for `-B`, `-C`, a forced add, `update-ref` and `symbolic-ref`. This record supersedes the parent's list-read sentence on that point.

- The worktree list is read once (`git_reads.clone_worktrees`), and only for these forms and the parent's. A read that fails refuses, even for a branch no worktree holds.
- Only a worktree other than the running tree counts as a holder. `git -C <dir>` names the running tree.
- Each git call in a chain is judged on its own.

Lane decisions:

- `update-ref` of a branch the running tree holds itself passes. The running tree is the holder, so no other tree is stale.
- `git -C <holder> <write>` counts as the holder's own tree and passes, `update-ref` included. The remedy text does not offer `update-ref` as the move path: it moves the ref alone, so the holder's index and files stay at the old commit. It names `git -C <holder> merge --ff-only <commit>`, which moves ref, index and files together, and `git worktree prune` for a holder whose folder is gone while the list still shows its branch.
- Own-tree `update-ref` of its own held branch leaves that tree's index stale, the same harm this rule stops across trees. The guard allows it as a stated gap. The gap is wider than the own tree: `-C` may name another session's tree, so `git -C <holder> update-ref refs/heads/x HEAD` or `-d` passes and leaves that holder's index stale. Debt `update-ref-in-holder-tree` holds it.
- Reads pass: `symbolic-ref HEAD` with no target, `update-ref` of a ref no worktree holds, and any ref outside `refs/heads/` (a remote-tracking ref).
- `update-ref --stdin` names its refs on stdin. The guard cannot read stdin, so it passes. This is a known gap, not a decision that it is safe.
- A plain `git push` is not refused. See the incident.

## The incident

Three sightings, named by the coordinator on 2026-11-08: review-record-post-check, lint-config-guard-paths and sim-tool-lease-check. Each was a branch moved or shared while another worktree held it. This repo records none of the three commands. The exact command of sim-tool-lease-check is unknown.

What was measured, in a scratch clone with git 2.43 (recorded in the red-case comments of `hooks/test_guard.py`): a plain `git push` moves no local ref. Git refuses a push into a branch that a worktree has checked out, in the same repository, and a push to origin changes only origin's ref. So a push alone did not cause the stale tree. The acts that move or share a held branch are `update-ref` and `symbolic-ref`: git 2.43 checks no worktree for either. A move from a tree that does not hold the branch left the holder's index at the old commit, with a staged diff that reverts the move.

Unmeasured: whether any of the three sightings ran `update-ref` or `symbolic-ref`. If one ran another form, this rule does not cover it.

## Harm it stops

The holder's files and index stay at the old commit while the branch moves. A commit there reverts the mover's work with a diff that looks like a normal edit. The same harm as the parent decision, through a call that decision did not read.

Remedy the refusal prints: the parent's detached checkout and push from the own worktree. To move the branch itself, `git -C <holder> merge --ff-only <commit>` from the tree that holds it. For a holder whose folder is gone, `git worktree prune`.

Known gap, filed as debt `subshell-cd-leaks-tree`: a `cd` inside a subshell sets the judged tree for the rest of the chain.

Kind: build
Plan: docs/decisions/held-branch-ref-moves.md#the-ruling (all)
