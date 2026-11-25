# Tests prove outcomes, run where their subject lives, and never fail on runner speed

## The ruling

A test must not fail on runner speed. CI runs a job only when its suites' files change, runs OS-independent suites on ubuntu only, and splits a near-cap job's slowest suite by family (a `ci-hygiene` step).

1. A skipped test reports SKIP with a count, never PASS. The fail-closed test list comes from the guard modules on disk.
2. No test times a run on a local device. Timed waits follow P5 of decision test-practices: no fixed sleep, hang guards allowed, and a verdict that depends on elapsed time uses a synthetic clock. One test
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
- macOS runs once per batch (R61, owner pick b, 2026-11-12 15:29 CST). A push to main starts no macOS runner: `shell-macos`, `checks-macos` and `checks-macos-b` skip it at job level, since a step-level skip still starts a runner. A pull request starts none of them (owner, 01:33 CST Nov 16 2026: "turn off all mac runs for now"): a manual run and a daily that runs start them. The lane workflow's macOS leg is the one exception on a pull request, for a draft that touches a macOS-tested file (`draft-until-reviewed`). `checks-macos` runs one mac-tagged slice of the guard suite (`GUARD_TESTS=macos-slice`, no shard) and `checks-macos-b` runs no guard step.
- The daily run (owner, item 880, the ask to free runner slots, 11:53 CST Nov 15) skips only when no push run on main came after the newest green daily, and that daily and the newest push run are at this head (owner ruling Q5 a, 13:44 CST Nov 23; owner pick on item 893, relayed 14:14 CST Nov 15). A push run since then runs the daily in full, proven or not. The `nightly-skip` job decides (`.github/scripts/nightly-skip.py`; rules in decision `push-skip-on-proven-tree`), and `scope` waits on it, so a skip reaches every job through `needs`. Nothing is cancelled: a cancelled run reads UNKNOWN and blocks merges. A failed read runs everything. The newest completed daily decides, so a skipped green daily never supersedes a red one.
- CI has one daily schedule (owner, item 880, 11:53 CST Nov 15; `47 8 * * *`). It replaces the no-nightly ruling (owner, 22:19 CST Nov 12: 45 nightly runs since Sep 30 found nothing the push runs had not). A push to main runs the Linux fast jobs only (every ubuntu job except the mutation jobs, the default reading). The mutation jobs run in the daily, in a pull request and in a manual run (`workflow_dispatch` stays). The 13 Windows shard jobs run in the daily and in a manual run only. A ready pull request runs the Windows slice in its two base jobs, `checks-windows-guard` and `checks-windows-merge`, and runs five flag-gated Windows jobs whole, plus the two launcher steps of `checks-windows-merge`, when their scope flag is set (decision `windows-prs-run-marked-tests`). The macOS jobs run in the daily and in a manual run only, not in a pull request (owner, 01:33 CST Nov 16), except the lane workflow's small macOS leg, which runs on a pull request that touches a macOS-tested file (owner, 22:09 CST Nov 24). Its draft-lane scope is the consultant's pick, undoable, not the owner's words. The `nightly-skip` job is live again. The newest schedule run on main is the schedule group's verdict in the red-main check. A push run never clears a red daily, because it skips the Windows, mutation and macOS jobs; a green manual run, which runs every job, does. macOS on main runs daily.
- Departs from: the no-nightly ruling above (owner, 22:19 CST Nov 12). It adds one daily schedule. The grant is the consultant's reading of item 880, relayed 12:06 CST Nov 15, not an owner-typed line.
- `concurrency` cancels superseded runs on pull requests only. Push and manual runs finish.
- Step names that `lint/rule_audit.py` reads do not change. The macOS guard step is the one rename: it is now "Guard fixture suite (macOS slice)", because its shard is gone, and no audit row cites it (`lint/rule_mechanisms.json`).
- When a CI job nears its time cap, split the slowest suite's subject by family into its own job, and give the measured CI time before and after. This is a step of the `ci-hygiene` skill (owner, 2026-10-17 23:46 CDT).

Reason: a slow Windows runner failed a PR on tests its change did not touch. Fixed sleeps cost time, and macOS CI minutes went to suites
that do not touch the OS. A duplicate run costs minutes for no new verdict.

Accepted risk: a defect in an OS-independent suite that shows only on macOS or Windows is not caught. Unmeasured.

Accepted risk (R61): the full guard suite no longer runs on macOS at all. Every event that starts a `checks.yml` macOS job (a manual run, or a daily that runs) runs the mac-tagged slice, and a push to main runs no macOS job. A draft pull request that touches a macOS-tested file runs those tests in the lane workflow's macOS leg (`draft-until-reviewed`), which narrows this risk for those tests only. The daily runs the macOS slice on main once a day. A macOS-only guard defect outside the slice reaches main and shows at the next daily, up to a day later. Unmeasured. The slice's tag comes from the darwin arms in `hooks/` (`MACOS_REACH` in `hooks/test_guard.py`, held to the arms by an ast scan).
Cost of `nightly-skip` (unmeasured): a runner on each push, pull request, manual run and the daily. It reads only on the daily. It makes a schedule runs read and push runs pages back to the green daily, and reads no jobs (see decision `push-skip-on-proven-tree`). It writes no file and sets no timer. The one timer is the daily cron.

Kind: process
Home: .github/workflows/checks.yml
