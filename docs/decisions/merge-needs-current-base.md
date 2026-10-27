# A merge needs a green run on the current base

## The ruling

Roadmap step c97, filed 2026-10-27: a batch merges only after a green run against the current main.

- The merge tool refuses a head that does not hold the base tip. The refusal names the fix: merge the base into the branch, push, and run again.
- It reads the head two times. The first read is before the claim, so nothing is claimed. The second read is after the check wait, on the base tip fetched then. A base that moved during the wait reverts the claim.
- A heal merge commit holds the base tip, so it passes. Its own checks wait before the merge.
- The preview prints a `base:` line that says whether the head holds the base tip.

Why: branch protection on `main` has `strict` false (`main-branch-protection`, main branch protection). GitHub reports BEHIND only when `strict` is on, so the tool's BEHIND refusal never fired. A batch could merge with a green run that never tested the main it lands on.

Risk: likely. Batches run while other batches merge, so main often moves under a green head. Landed 2026-10-27.

Kind: process
Home: merge/merge.py
