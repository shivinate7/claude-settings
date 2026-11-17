# A merge needs a clean merge with the base tip, and a green run or a lane-lint PASS

## The ruling

Owner pick A for R42 part 2 (per-lane merge). Rule M3, per lane: the head must merge cleanly with the base tip. Its own run must be green, or still pending under a lane-lint PASS that names its live head. The head need not hold the tip. At merge time the tool does one merge of main into the head and keeps the green run (decision `lane-main-in-at-merge-time`).

Owner ruling `own-merge-on-lint-pass` (owner, 2026-11-15 18:21 CST, typed "B for sure") added the pending case. Main's run after the merge is the check, and a red main reverts the blamed commit.

- The run read is one read, with no wait under the lock. The lint proof is asked only when the read says the head is pending. A pending head with no PASS stops the merge at that read.
- A PASS lifts a pending run only for the head it names. It carries to the live head over claim commits. For a PR that replaces a source PR, it also carries over an identical tree. Any other PASS refuses.
- A finished red run refuses. A red main refuses too, except its revert (`git-red-main-reverts`).
- The clean merge is `git merge-tree --write-tree` of the head and the base tip. `confirm` reads it before the claim and again after the claim push. A conflict refuses. So does a read that cannot run.
- A confirm that must push a claim commit pushes it and stops. The next confirm merges the claim head once its run is green, or pending under a PASS that carries over the claim commit.
- The tool sends its PUT past a BLOCKED read only when a PASS lifted the pending run. BEHIND still refuses.
- The batch's wait for the base to move, the heal merge commit and the small-move suite run are gone.

Why: branch protection on `main` has `strict` false, so GitHub reports BEHIND only when `strict` is on (`main-branch-protection`). The tool's own reads are the gate.

Residual risk: a clean merge can still break a suite, and a head can merge before its own run ends. Main's run after the merge finds it. A red main is then held under the red-main rule (`git-red-main-reverts`) until its revert merges with its tree proven.

Kind: process
Home: merge/merge.py

Cost: per merge, one read of the head's run and two `git merge-tree --write-tree` starts (unmeasured). A pending head adds one paged read of the repo's comments and the carry checks (unmeasured).

Risk: likely. Lanes merge while main moves, so main often moves under a green or pending head.
