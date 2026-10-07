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
- B. On a pull request, a suite runs only when its inputs change. An unmapped changed path
  runs everything.
- C. On a pull request, the Windows merge job runs only the Windows-specific merge tests.
- D. Make `merge/test_merge.py` faster, with the same cases and verdicts. Tried and dropped
  on 2026-10-07. Setup takes 31% of the time, and the `git` calls inside `merge.py` take 69%.
  Reusing one setup saved about 9%, under the 20% bar. C covers the PR wait instead.
- C, as built: on a pull request, Windows runs a 14-test slice (`MERGE_TESTS=windows-slice`).
  Push, nightly and manual runs keep the full suite. `lint/test_windows_split.py` fails when
  the slice runs on push or the full Windows run is lost.

A push to main, the nightly run and a manual run always run every suite on every OS.

## Accepted risk

B and C can miss a break on a pull request. The push to main and the nightly run catch it
after the merge. A does not lose coverage.
