# A merge deletes its batch's lane branches

## The ruling

Owner, 2026-10-19 12:14 CDT: each merge deletes the lane branches its batch took in.

An open PR at its lane tip is done when its base is the batch base or another lane in the same batch. So a whole stack merged in one batch is deleted.

The local side goes too (owner, 2026-10-25, step c44). Each local branch at a lane tip, by any name, gets the PR branch's own local cleanup. Its worktree goes when the sweep's `--fast` judgment says reap. The branch goes when its tip is in the merge commit. A lane whose remote head stays keeps its local side. So does a name in `merge.keepBranches`. A failed remote or open-PR read touches nothing local. GitHub's `delete_branch_on_merge` often deletes the remote lane heads first, and the local pass still runs then.

A lane is kept, with a line, when:

- an open PR outside the batch has it as its base (a partial stack);
- an open PR at its tip aims at another base (a backport); or
- an open PR's head sha differs from the tip.

A head with two or more open PRs is judged on all their bases.

Outcome protected: origin keeps only live lanes. Lane branches that outlive their batch pile up on origin. Later
sessions read them as open work, and they mislead the next batch.

Reason for the open-PR rule, as measured: GitHub marks a lane PR merged a median of 2 s after its batch merges
(minimum 1 s, over 40 lane PRs). The cleanup reads open PRs at about that moment, so a lane PR can still read open.
An open PR whose head is the lane tip has all its commits on main already, so it does not block the delete.

Reason for the stack rule, as measured: 5 of the last 500 PRs here were stacked PRs, and none was a backport.
PR #456 on map-skill-move is open today.

## The design

Built on branch `merge-cuts-lanes` (commit 1cae7c63), in `merge/merge.py`: `lane_tips`, `cut_lanes` and
`Host.open_heads`.

- Before the merge, `lane_tips` reads the lane tips: parent 2 and later of each merge commit in `base..sha`,
  less any commit already on the base.
- After the merge, `cut_lanes` takes only origin heads whose sha equals a tip.
- It skips the default branch, the PR base and the PR's own branch. Those are not lanes, so they print no line.
- It keeps a head named in `merge.keepBranches`.
- An open PR at a lane tip is done when its base is the batch base or another lane of the same batch. A whole
  stack merged in one batch is deleted with it.
- It keeps a lane, with a line, when an open PR whose head is not a lane of this batch has the lane as its base
  (a partial stack).
- It keeps a lane, with a line, when an open PR at its tip aims at any other base (a backport).
- It keeps a lane, with a line, when every merge that took its tip into the batch was reverted on the batch (a
  "This reverts commit" message, counted through reverts of reverts). The tool refuses such a batch before the claim
  (`refuse_dropped_lane`), so this line is a fallback: a revert on main deletes the lane's files when the lane
  later merges main (incident: batch #663 dropped the platform-ask lane by a revert, and it lost 11 of 13 files). The remedy: rebuild the batch branch from main without the lane.
- It keeps a head whose open PR has a head sha that differs from the tip.
- A head with two or more open PRs is judged on all their bases, by the rules above.
- `Host.open_heads` raises on a failed read, or on 1000 or more rows. Then no head is deleted.
- It keeps a head whose tip is neither an ancestor of the merge commit nor patch-equal to it, per
  `guard_core.branch_cherry_empty`. The patch test is in `a-branch-is-redundant-by-patch-not-by-ancestry`, a
  branch is redundant by patch, not by ancestry.
- It deletes each other head with `git push --force-with-lease=refs/heads/<branch>:<tip>`.
- Every lane prints one line: deleted, or kept with the reason. This includes an unreadable open-PR read and a
  lane not found at its tip.
- It never fails the merge. An unexpected error prints one line.

The cleanup runs only when `merge.deleteBranch` is true. An absent key reads as false, so no lane is deleted.

Note: a squash-merged lane has no merge commit parent, so no tip is read. Its branch is kept. The design does not
prove that a squash-merged lane landed.

Kind: process
Home: merge/merge.py

## Holes, named

- (a) Any origin head at a lane tip's sha is deleted. `merge.keepBranches` is the only guard, so a long-lived branch merged into a batch is lost. Its commits stay on main; restoring it is one push. Debt: `long-lived-head-lost-in-batch`.
- (b) A fast-forwarded first lane is never a tip (0 of 112 recent lane merges did this). Debt: `ff-first-lane-not-a-tip`.
- (c) Squash-merged lanes are kept. Debt: `squash-lane-branch-kept`.
- (d) A merge tool older than this change refuses main's stamp.json (unknown field `keepBranches`) with a clear stop. `merge/install_from_main.sh` fixes it. Debt: `old-merge-tool-refuses-stamp`.
- (e) In a cycle of lanes (A based on B, and B based on A), the delete order is the heads order, not dependents first. A failed delete in the cycle can then close a PR whose base is gone. Debt: `lane-cycle-delete-order`.
