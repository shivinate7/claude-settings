# Docs-only pull requests skip the code suites; PR runs skip duplicate work

## What was measured

gates-windows took about 12 min on a pull request. Two steps were repeats. The
unknown-read contract check reran all of `hooks/test_install_src.sh` (about 148 s on
Windows) for two cases. The Janitor sweep mutation harness ran on every OS.

## The ruling

- `hooks/test_install_src.sh` takes case names as arguments and runs only those. No
  arguments runs all. `lint/check_unknown_reads_contract.py` passes `caseF4 caseF6`.
  The cases keep one home.
- Janitor sweep mutation harness: on a pull request it runs on ubuntu only, as the
  Guard mutation harness already does. A push, the nightly run and a manual run keep it
  on every OS.
- `.github/scripts/harness-scope.sh` runs once, in the `scope` job. It writes one flag
  per gate job, plus `code`, `guard` and `sweep`. On a pull request whose diff it can
  read, a flag is on only when a changed path is an input of that job. A push, a nightly
  run, a manual run, an unreadable or empty diff, or an unmapped path turns every flag on.
  The detector stays one script. `lint/test_harness_scope.py` pins the map.
- Every gate job but `gates` has `needs: scope` and a job-level `if:` on its own flag, so
  a skipped job starts no runner (decision ci-wall-time-cuts, cut B). A docs-only PR runs
  only `gates`.
- These always run in `gates`: rule audit, ruling census, ruling home, stamp, STE lint,
  record slugs, and the other lints.
- Why the skipped suites are safe: grep of `hooks/test_guard.py`,
  `hooks/test_ruling_home.py` and `actions/stamp/test_stamp.mjs` found no read of the
  live `CLAUDE.md` or `decisions/`. Each builds its own fixture tree.
- main has no branch protection. The merge tool reads `.github/stamp.json`
  requiredChecks, and it reads a skipped job as passing (`merge/test_merge.py`,
  `test_a_required_check_that_is_skipped_reads_green`). A failed `scope` job is red, so a
  skip caused by it cannot pass.

## Accepted risk

A skipped suite that reads a live `.md` file would miss a break on a pull request. The
nightly run and the push to main run everything, so the miss shows there.
