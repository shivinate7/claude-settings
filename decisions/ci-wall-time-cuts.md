# Cut CI wall time: split Windows, scope suites, slim the Windows merge run

## The ruling

Owner, 2026-10-07 (A to D) and 2026-10-10 (F). Windows is the PR wait because it starts thousands of short processes. The repo is public, so wall time is the only cost.

- A. `gates-windows` is split into parallel Windows jobs. Every Windows suite runs in exactly one. `lint/test_windows_split.py` holds the suite list and fails on a dropped or duplicated suite.
- B. A `scope` job runs first. Each other job skips at job level, with no runner, when none of its inputs changed. A docs-only PR runs only `gates`. In `gates`, the guard and sweep suites also skip by input. An unmapped path runs everything. `lint/test_harness_scope.py` pins the path map. `docs-only-prs-skip-code-suites` holds the detector's rules.
- C. On a pull request, Windows runs a slice of the merge tests (`MERGE_TESTS=windows-slice`). `lint/test_windows_split.py` fails when the slice runs on push or the full Windows run is lost.
- F. The Windows guard suite runs in its own parallel Windows job. The guard mutation harness runs in its own Linux job. On a pull request, Windows runs a slice of the guard cases that touch Windows code (`GUARD_TESTS=windows-slice`). `lint/test_windows_split.py` and `lint/test_harness_scope.py` pin both.
- No macOS slice: macOS ends before Windows, so a slice would not shorten the PR wait. The ci-hygiene skill, step 17, keeps the pattern for private repos.

A push to main, the nightly run and a manual run always run every suite on every OS.

Accepted risk: B, C and F can miss a break on a pull request, as can a missed input in B's path map. The push to main and the nightly run catch it after the merge. A loses no coverage.

Kind: process
Home: lint/test_windows_split.py
