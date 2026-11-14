# A merge needs a green run on its own base and a clean merge with the base tip

## The ruling

Owner pick A for R42 part 2 (per-lane merge). Rule M3, per lane: the head must already be green on its own base, and it must merge cleanly with the base tip. The head need not hold the tip.

- The green read is one read, with no wait under the lock.
- The clean merge is `git merge-tree --write-tree` of the head and the base tip. `confirm` reads it before the claim and again after the claim push. A conflict refuses. So does a read that cannot run.
- A confirm that must push a claim commit pushes it and stops. The next confirm merges a green claim head.
- The batch's wait for the base to move, the heal merge commit and the small-move suite run are gone.

Why: branch protection on `main` has `strict` false, so GitHub reports BEHIND only when `strict` is on (`main-branch-protection`). The tool's own reads are the gate.

Residual risk: a clean merge can still break a suite. Main's run after the merge finds it. A red main is then held under the red-main rule (`git-red-main-reverts`) until its revert merges. Merges then resume, with the revert's own run still going.

Kind: process
Home: merge/merge.py

Cost: per merge, one green read of the head and two `git merge-tree --write-tree` starts (unmeasured).

Risk: likely. Lanes merge while main moves, so main often moves under a green head.
