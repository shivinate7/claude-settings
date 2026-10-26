# c64: a slow browser install never cancels the gates job

Cloud build thread brief. Build advisor (2), Oct 26, against claude-settings main 12d9851.
Base: main 12d9851; never rebase onto main after review. Push roadmap edits to the branch only;
only "Triage the roadmap (3)" (cmsg_01DoF7thf3iq2Srr1UsfXgh254YqfUUZHeznzPGp4b6a8B) republishes the
roadmap page and takes new steps. Send heads to "Advise the claude-settings build (2)".

## Incident

Batch PR #603, run 40302813024: the `gates` job (timeout-minutes 36) was cancelled inside the
"shoot fixture suite" step. `playwright install --with-deps chromium` spent over 11 min on slow
azure apt mirrors (single packages 1 to 5 min); on #595's run the step took 27 s. No test failed.
The lint job, which always runs, lost its whole verdict to one install.

## Task

1. Move the shoot suite out of the `gates` job into its own job, gated by the same `shoot` scope
   flag, with its own timeout-minutes sized from measured runs. Add it to whatever aggregates the
   required checks, if anything does, so a red shoot suite still blocks.
2. Cut the install time where cheap: install only the browser (no `--with-deps`) if the runner
   image already has the libraries, or cache the Playwright browser by its lockfile hash. Measure
   both on a dispatch run and pick by the numbers; say which in the PR.
3. The `gates` job's cap stays as it is; it should no longer hold the browser install.

## Failure classes and proof

- Proof: a dispatch run where the shoot job runs its full suite green and the gates job no longer
  contains the step. The test count of lint/test_shoot.mjs is the same as before.
- False green: a skipped shoot job must not read as passing when the scope flag is on.
- lint/test_harness_scope.py and lint/test_gates.py stay green; extend them if they pin job names.
- A fresh Sonnet reviewer reads the diff.

## Report

Cap 15 lines: Done, Deviations, Next. No question for shiv: park any in the PR body.
