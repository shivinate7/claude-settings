# A merge deletes its batch's lane branches

## The ruling

Owner, 2026-10-19 12:14 CDT: each merge deletes the lane branches its batch took in.

Outcome protected: origin keeps only live lanes. Lane branches that outlive their batch pile up on origin. Later
sessions read them as open work, and they mislead the next batch.

## The design

Built on branch `merge-cuts-lanes` (commit 1cae7c63), in `merge/merge.py`: `lane_tips`, `cut_lanes` and
`Host.open_heads`.

- Before the merge, `lane_tips` reads the lane tips: parent 2 and later of each merge commit in `base..sha`,
  less any commit already on the base.
- After the merge, `cut_lanes` takes only origin heads whose sha equals a tip.
- It skips the default branch, the PR base and the PR's own branch.
- It keeps a head named in `merge.keepBranches`.
- It keeps a head with an open PR. `Host.open_heads` raises on a failed read, or on 1000 or more rows. Then no
  head is deleted.
- It keeps a head whose tip is neither an ancestor of the merge commit nor patch-equal to it, per
  `guard_core.branch_cherry_empty`. The patch test is in `a-branch-is-redundant-by-patch-not-by-ancestry`, a
  branch is redundant by patch, not by ancestry.
- It deletes each other head with `git push --force-with-lease=refs/heads/<branch>:<tip>`.
- It prints one line per lane: deleted, or kept with the reason.
- It never fails the merge. An unexpected error prints one line.

The cleanup runs only when `merge.deleteBranch` is true. The default is true.

Note: a squash-merged lane has no merge commit parent, so no tip is read. Its branch is kept. The design does not
prove that a squash-merged lane landed.

Kind: process
Home: merge/merge.py

## Holes, named
