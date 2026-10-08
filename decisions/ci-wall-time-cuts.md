# Cut CI wall time: split Windows, scope suites, slim the Windows merge run

## What was measured

Last 10 green pull-request runs of `gates`, 2026-10-07. On a code PR, `gates-windows` took
904-1243 s, and it was the whole wait. Linux took 268-480 s, and macOS 267-388 s. Windows
step times (run 37662102373): merge suite 464 s, guard 263 s, `install.sh` 180 s, stamp
engine 85 s, janitor sweep 67 s. The cause is the cost of starting a process on Windows. The
suites start thousands of short `git`, `python` and `bash` processes. The repo is public, so
runner minutes are free, and wall time is the only cost.

## The ruling

The owner chose all four cuts on 2026-10-07. Each lands as its own PR.

- A. Split `gates-windows` into parallel Windows jobs. Every Windows suite runs in exactly one
  of them. `lint/test_windows_split.py` holds the suite list and fails on a dropped or
  duplicated suite. PR 277's time caps for `pointer-windows` and `shell-macos` fold into A,
  and PR 277 closes as superseded.
- B. A `scope` job runs first. Each other job skips at job level, with no runner, when none
  of its inputs changed. A docs-only PR runs only `gates`. In `gates`, the guard and sweep
  suites also skip by input. An unmapped path runs everything. The owner chose job-level
  skips over step-level skips on 2026-10-07: the goal is fewer runs and billed minutes.
  `lint/test_harness_scope.py` pins the path map. Decision docs-only-prs-skip-code-suites
  holds the detector's rules.
- C. On a pull request, Windows runs a slice of the merge tests (`MERGE_TESTS=windows-slice`).
  Push, nightly and manual runs keep the full suite. `lint/test_windows_split.py` fails when
  the slice runs on push or the full Windows run is lost.
- D. Make `merge/test_merge.py` faster, with the same cases and verdicts. Tried and dropped
  on 2026-10-07. Setup takes 31% of the time, and the `git` calls inside `merge.py` take 69%.
  Reusing one setup saved about 9%, under the 20% bar. C covers the PR wait instead.
- E. Dropped on 2026-10-08. The plan was a macOS slice on pull requests, like C. On PR 296,
  guard (197 s) and janitor sweep (93 s) took 290 of about 390 s in `gates-macos`. Both hold
  macOS code (the `ps -o lstart=` liveness read, darwin branches in `janitor/sweep.py`), so E
  needed a new test selector in each suite. The repo is public, so macOS minutes are free. macOS
  ends before Windows (about 9 min), so the PR wait does not change. The ci-hygiene skill, step
  17, keeps the pattern for private repos.

A push to main, the nightly run and a manual run always run every suite on every OS.

## Accepted risk

B and C can miss a break on a pull request. A missed input in B's path map has the same effect. The push to main and the nightly run catch it
after the merge. A does not lose coverage.
