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
- The macOS job runs only the suites that touch the OS. The `install.sh` tests run on Linux and macOS: `checks-merge-install` runs them on Linux, where cloud sessions install, and `shell-macos` runs them on macOS (R63, owner pick a, 2026-11-12 15:55 CST: keep both runs). Windows keeps its own Git Bash run.
- macOS runs once per batch (R61, owner pick b, 2026-11-12 15:29 CST). A push to main starts no macOS runner: `shell-macos`, `checks-macos` and `checks-macos-b` skip it at job level, since a step-level skip still starts a runner. A pull request, the nightly and a manual run still start them. `checks-macos` runs one mac-tagged slice of the guard suite (`GUARD_TESTS=macos-slice`, no shard) and `checks-macos-b` runs no guard step.
- The nightly skips when main's head has a green push run of `checks.yml` and the newest completed nightly is green. The `nightly-skip` job decides (`.github/scripts/nightly-skip.py`), and `scope` waits on it, so a skip reaches every job through `needs`. Nothing is cancelled: a cancelled run reads UNKNOWN and blocks merges. A failed read runs everything. The newest completed nightly decides, so a skipped green nightly never supersedes a red one.
- Linux and Windows run each suite once per integration PR, on the integration PR run (R62, owner 2026-11-12 15:55 CST: "A for sure, B seems good too"). `checks-windows-rest` runs in two parallel jobs, `checks-windows-rest` and `checks-windows-rest-2`, each capped at a provisional 60 min and each suite in one of them; the split is a bandaid, since the cost is Windows process start. On a ready pull request the Windows guard shards, the Windows merge shards and both rest jobs run in full whatever the scope flags say, on no draft, and a push, the nightly and a manual run keep their flag rules. The full shards are held, not dropped: the owner worries that untagged cases act differently on Windows. The Windows slice steps are gone, since shard 1 runs on a ready PR. Every other job runs on a ready PR under its scope flags, as on any PR, except that a ready PR from a `batch-*` branch (the integration PR) sets every scope flag on (`ci-scope.sh`), so its run is the all-flags run. The janitor sweep mutation steps of `checks-macos` and `checks-windows-sweep` also run on a ready PR, on the sweep flag alone: only the platform flag is ignored (the lane's choice, following triage's 17:53 CST Nov 12 message on step `ci-linux-windows-once`; no ruling record). The `push-skip` job (`.github/scripts/push-skip.py`) skips a push to main only when the push commit's tree equals the tree of a `batch-*` PR head whose ready run passed `all-jobs-passed`, so a push skips only when that run was green on the same tree. It reads that check run, not the `checks.yml` run's conclusion, because a draft run skips every job and concludes success; a run still queued or in progress is not green. `scope` waits on it, so a skip reaches every job through `needs`, the run is a completed success, and nothing is cancelled. A failed read of any kind runs everything. The lane touched-tests checkouts fetch depth 50 and deepen until the base and head share a merge base.
- `concurrency` cancels superseded runs on pull requests only. Push, nightly and manual runs finish.
- Step names that `lint/rule_audit.py` reads do not change. The macOS guard step is the one rename: it is now "Guard fixture suite (macOS slice)", because its shard is gone, and no audit row cites it (`lint/rule_mechanisms.json`).
- When a CI job nears its time cap, split the slowest suite's subject by family into its own job, and give the measured CI time before and after. This is a step of the `ci-hygiene` skill (owner, 2026-10-17 23:46 CDT).

Reason: a slow Windows runner failed a PR on tests its change did not touch. Fixed sleeps cost time, and macOS CI minutes went to suites
that do not touch the OS. A duplicate run costs minutes for no new verdict.

Accepted risk: a defect in an OS-independent suite that shows only on macOS or Windows is not caught. Unmeasured.

Accepted risk (R61): the full guard suite no longer runs on macOS at all. Every event that starts a macOS job (a pull request, the nightly, a manual run) runs the mac-tagged slice, and a push to main runs no macOS job. A macOS-only guard defect outside the slice reaches main and is not caught. Unmeasured. The slice's tag comes from the darwin arms in `hooks/` (`MACOS_REACH` in `hooks/test_guard.py`, held to the arms by an ast scan).
Accepted risk (R62): a push whose tree a green integration PR head already has runs no job. A `batch-*` ready PR runs every scope flag, so that run was the all-flags run, and a push skip rests on it. The nightly's skip reads a `push-skip` run as main's green push run, so it can skip too. Unmeasured. The full Windows suites and the sweep mutation steps now cost every ready PR run time they did not cost before. Unmeasured.
Cost of `nightly-skip`: one runs read per nightly (two `GET` calls on the Actions runs API), unmeasured. It starts no process beyond its own job, writes no file and sets no timer.
Cost of `push-skip`: one pull request list read per push, then per integration PR head its commit and its `all-jobs-passed` check runs (three reads for one integration PR head: the list, its commit, its check runs), unmeasured. It starts no process beyond its own job, writes no file and sets no timer.

Kind: process
Home: .github/workflows/checks.yml
