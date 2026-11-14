# Tests prove outcomes, run where their subject lives, and never fail on runner speed

## The ruling

A test must not fail on runner speed. CI runs a job only when its suites' files change, runs OS-independent suites on ubuntu only, and splits a near-cap job's slowest suite by family (a `ci-hygiene` step).

1. A skipped test reports SKIP with a count, never PASS. The fail-closed test list comes from the guard modules on disk.
2. No test times a run on a local device. Fixed sleeps and wall-clock bounds are in P5 of decision test-practices (no sleep or clock in a test). One test
   checks that the code follows a speed best practice, such as a count of calls or cache hits.
3. One shared set of fixtures: one git template, and one fake each for `gh`, `claude` and `xcrun`.
4. The pure-parse guard families run in one Python process. The cases that need a real hook process stay as subprocess cases.
5. A test stays only when it names the real failure it catches: a wrong allow or deny, lost work, a stuck merge, or a wrong record (test-practices P2, red run). A test that pins a known finding
   becomes a debt, not a test.
6. A merge of look-alike tests keeps one row for each item in a guard's list, each part of its pattern, and each filter. A row that alone
   fails when that item goes stays.

## Where CI runs a suite

- Each CI job runs only when a file that its suites read changes.
- OS-independent suites and pure lints run on ubuntu only: rule audit (suite and lint), record slugs, mod version bumps, landed dirs, agent models, STE lints, zizmor.
- The ruling census suite stays on every OS: it tests macOS `/var` symlinks and Windows backslash and `normcase` paths.
- Suites that touch paths, processes, shells, launchd, schtasks, symlinks or encoding run on every OS. When unsure, a suite stays on all OSes.
- The macOS job runs only the suites that touch the OS. `install.sh` syntax and checkout detection run once, on `shell-macos`. Windows keeps its own Git Bash run.
- macOS runs once per batch (R61, owner pick b, 2026-11-12 15:29 CST). A push to main starts no macOS runner: `shell-macos`, `checks-macos` and `checks-macos-b` skip it at job level, since a step-level skip still starts a runner. A pull request and a manual run still start them. `checks-macos` runs one mac-tagged slice of the guard suite (`GUARD_TESTS=macos-slice`, no shard) and `checks-macos-b` runs no guard step.
- Until the nightly was dropped (owner, 22:19 CST Nov 12), it skipped when main's head had a green push run of `checks.yml` and the newest completed nightly was green. The `nightly-skip` job decided (`.github/scripts/nightly-skip.py`), and `scope` waited on it, so a skip reached every job through `needs`. Nothing was cancelled: a cancelled run reads UNKNOWN and blocks merges. A failed read ran everything. The newest completed nightly decided, so a skipped green nightly never superseded a red one.
- CI has no nightly schedule (owner, 2026-11-12 22:19 CST). 45 nightly runs since Sep 30 found nothing the push runs had not. A manual run stays through `workflow_dispatch`. The job that ran only on `schedule`, `nightly-skip`, is now dead. It stays until a cleanup, and the cleanup keeps `.github/scripts/nightly-skip.py`, because other code loads it as the one reader of the runs API. The newest schedule run on main stays the schedule group's verdict in the red-main check. A push run never clears a red schedule run, because it skips the macOS jobs. macOS on main now runs only on a manual run. The 45-run basis predates the macOS cut (R61), so it does not cover macOS.
- `concurrency` cancels superseded runs on pull requests only. Push and manual runs finish.
- Step names that `lint/rule_audit.py` reads do not change. The macOS guard step is the one rename: it is now "Guard fixture suite (macOS slice)", because its shard is gone, and no audit row cites it (`lint/rule_mechanisms.json`).
- When a CI job nears its time cap, split the slowest suite's subject by family into its own job, and give the measured CI time before and after. This is a step of the `ci-hygiene` skill (owner, 2026-10-17 23:46 CDT).

Reason: a slow Windows runner failed a PR on tests its change did not touch. Fixed sleeps cost time, and macOS CI minutes went to suites
that do not touch the OS. A duplicate run costs minutes for no new verdict.

Accepted risk: a defect in an OS-independent suite that shows only on macOS or Windows is not caught. Unmeasured.

Accepted risk (R61): the full guard suite no longer runs on macOS at all. Every event that starts a macOS job (a pull request or a manual run) runs the mac-tagged slice, and a push to main runs no macOS job. With the nightly dropped, no macOS job runs on main unless someone starts a manual run. A macOS-only guard defect outside the slice reaches main and is not caught. Unmeasured. The slice's tag comes from the darwin arms in `hooks/` (`MACOS_REACH` in `hooks/test_guard.py`, held to the arms by an ast scan).
Cost of `nightly-skip`, dead since the nightly was dropped: one runs read per nightly (two `GET` calls on the Actions runs API), unmeasured. It starts no process beyond its own job, writes no file and sets no timer.

Kind: process
Home: .github/workflows/checks.yml
