# A merge needs a green run on the current base

## The ruling

Roadmap step c97, filed 2026-10-27; step c150, 2026-10-28: a batch merges only after a green run that holds for the current main.

- The merge tool refuses a head that does not hold the base tip. The refusal names the fix: merge the base into the branch, push, and run again. It also says why the green run cannot stand.
- A small move is the one exception: the green run stands when all of these hold, and any read that fails refuses.
  - The paths main changed since the merge base share no path with the batch's paths. The records page is the one exception, because the generator proves it on the merge.
  - The head and the base tip merge cleanly.
  - `.github/scripts/ci-scope.sh`, run on that merge, turns on no job and no suite for main's paths. A repo without the script gets no exception.
  - On that merge, `bin/ci-job gates --lint --base <base>` passes, and so does each suite in merge.py `DOC_SUITES`, the `gates` suites outside `--lint` that read tracked docs.
- It reads the head two times, with the same check. The first read is before the claim, so nothing is claimed. The second read is after the check wait, on the base tip fetched then. A base that moved during the wait, and is not a small move, reverts the claim.
- A heal merge commit holds the base tip, so it passes. Its own checks wait before the merge.
- The preview prints a `base:` line that says whether the head holds the base tip, is a small move, or is BEHIND.

Why: branch protection on `main` has `strict` false (`main-branch-protection`, main branch protection). GitHub reports BEHIND only when `strict` is on, so the tool's BEHIND refusal never fired. A batch could merge with a green run that never tested the main it lands on. A docs merge to main cannot change a code job, but it can break a cross-file lint, so the lints run on the merge.

Cost of a small move check: only when the head lacks the base tip, at most three times per merge. Each check starts about 10 git processes, one ci-scope run, one ci-job run (two processes per lint step, about 50 steps, about 4 minutes) and one process per doc suite. It writes one temp file, and keeps one ci-job log only on a failure. The lock is extended to cover each lint run.

Risk: likely. Batches run while other batches merge, so main often moves under a green head. Landed 2026-10-27; the small move 2026-10-28.

Kind: process
Home: merge/merge.py
