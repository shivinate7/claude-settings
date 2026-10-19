# A merge deletes its batch's lane branches

## The ruling

Owner, 2026-10-19 12:14 CDT: each merge deletes the lane branches its batch took in.

Owner, 2026-10-19 14:48 CDT: an open PR blocks a lane's delete only when its head sha differs from the lane tip.

Outcome protected: origin keeps only live lanes. Lane branches that outlive their batch pile up on origin. Later
sessions read them as open work, and they mislead the next batch.

Reason for the open-PR rule, as measured: GitHub marks a lane PR merged a median of 2 s after its batch merges
(minimum 1 s, over 40 lane PRs). The cleanup reads open PRs at about that moment, so a lane PR can still read open.
An open PR whose head is the lane tip has all its commits on main already, so it does not block the delete.

## The design

Built on branch `merge-cuts-lanes` (commit 1cae7c63), in `merge/merge.py`: `lane_tips`, `cut_lanes` and
`Host.open_heads`.

- Before the merge, `lane_tips` reads the lane tips: parent 2 and later of each merge commit in `base..sha`,
  less any commit already on the base.
- After the merge, `cut_lanes` takes only origin heads whose sha equals a tip.
- It skips the default branch, the PR base and the PR's own branch. Those are not lanes, so they print no line.
- It keeps a head named in `merge.keepBranches`.
- It keeps a head with an open PR whose head sha differs from the tip. An open PR at the tip with the batch's
  base does not keep it. At the tip with another base, it does (a backport).
- It keeps a head with two or more open PRs ("more than one open PR").
  `Host.open_heads` raises on a failed read, or on 1000 or more rows. Then no head is deleted.
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
- (d) For a head with two open PRs, the first row's base is lost. A stacked PR on a same-batch lane can then be closed, depending on row order (`merge/merge.py`, `Host.open_heads`). Fix: keep the bases as a set. Debt: `two-open-prs-lose-first-base`.
- (e) A merge tool older than this change refuses main's stamp.json (unknown field `keepBranches`) with a clear stop. `merge/install_from_main.sh` fixes it. Debt: `old-merge-tool-refuses-stamp`.
