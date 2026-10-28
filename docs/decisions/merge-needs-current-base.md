# A merge needs a green run on the current base

## The ruling

Roadmap step c97, filed 2026-10-27; step c150, 2026-10-28: a batch merges only after a green run that holds for the current main.

- The merge tool refuses a head that does not hold the base tip. The refusal names the fix: merge the base into the branch, push, and run again. It also says why the green run cannot stand.
- A small move is the one exception: the green run stands when all of these hold, and any read that fails refuses.
  - The paths main changed since the merge base share no path with the batch's paths. The records page is the one exception, because the generator proves it on the merge.
  - The head and the base tip merge cleanly.
  - `.github/scripts/ci-scope.sh`, run on that merge, turns on no job and no suite for main's paths. A repo without the script gets no exception.
  - On that merge, `bin/ci-job gates --lint --base <base>` passes.
  - On that merge, each other `gates` suite that may read one of main's paths passes. The suites come from the workflow, not a list. All of them share a 1200 s budget. The records page is not matched: the records are.
    - A Python suite, read with `ast`, is hit when its source names the exact path or file name anywhere. A folder below the top or a stem is a hit only in two forms. One is a string joined or divided onto a root bound from `__file__`. The other is a string given bare to a file reader such as `open` or `os.listdir`. A root taken whole by a call, as by a walk, hits every path under its folder. A folder named only under a temp dir is no hit. A suite `ast` cannot parse refuses.
    - A node or bash suite is hit when its source names any of those words.
- It reads the head two times, with the same check. The first read is before the claim, so nothing is claimed. The second read is after the check wait, on the base tip fetched then. A base that moved during the wait, and is not a small move, reverts the claim.
- A heal merge commit holds the base tip, so it passes. Its own checks wait before the merge.
- The preview prints a `base:` line that says whether the head holds the base tip, is a small move, or is BEHIND.

Why: branch protection on `main` has `strict` false (`main-branch-protection`, main branch protection). GitHub reports BEHIND only when `strict` is on, so the tool's BEHIND refusal never fired. A batch could merge with a green run that never tested the main it lands on. A docs merge to main cannot change a code job, but it can break a cross-file lint, so the lints run on the merge.

Cost of a small move check: only when the head lacks the base tip, at most three times per merge. Each check starts about 10 git processes, one ci-scope run, two ci-job runs (a plan, and the lints at two processes per step, about 50 steps, about 4 minutes) and one process per hit suite. A records-only move (a new record and the page) hits 6 suites, about 50 s in all; the whole check took 4 min 43 s on this repo (measured 2026-10-28). It writes one temp file, and keeps one ci-job log only on a failure. The lock is extended to cover each lint run.

Residual risk: some suites that read a doc are not hit. One reads it only through an imported helper. One reads it through a root not bound from `__file__`, such as an attribute, an argument or a path built from names. One walks the whole repo. Node and bash suites are matched by words only, which fails safe.

Risk: likely. Batches run while other batches merge, so main often moves under a green head. Landed 2026-10-27; the small move 2026-10-28.

Kind: process
Home: merge/merge.py
