# Tests prove outcomes, run where their subject lives, and never fail on runner speed

## The ruling

A test must not fail on runner speed. CI runs a job only when its suites' files change, runs OS-independent suites on ubuntu only, and splits a near-cap job's slowest suite by family (a `ci-hygiene` step).

1. A skipped test reports SKIP with a count, never PASS. The fail-closed test list comes from the guard modules on disk.
2. No test waits on a fixed sleep or a wall-clock bound. A test uses a marker file, a ratio to a same-process baseline, or an injected
   clock. No test times a run on a local device. One test checks that the code follows a speed best practice, such as a count of calls
   or cache hits.
3. One shared set of fixtures: one git template, and one fake each for `gh`, `claude` and `xcrun`.
4. The pure-parse guard families run in one Python process. The cases that need a real hook process stay as subprocess cases.
5. A test stays only when it names the real failure it catches: a wrong allow or deny, lost work, a stuck merge, or a wrong record. A test
   that pins a known finding becomes a debt, not a test.
6. A merge of look-alike tests keeps one row for each item in a guard's list, each part of its pattern, and each filter. A row that alone
   fails when that item goes stays.

## Where CI runs a suite

- Each CI job runs only when a file that its suites read changes.
- OS-independent suites and pure lints run on ubuntu only: rule audit (suite and lint), record slugs, mod version bumps, landed dirs, agent models, STE lints, zizmor.
- The ruling census suite stays on every OS: it tests macOS `/var` symlinks and Windows backslash and `normcase` paths.
- Suites that touch paths, processes, shells, launchd, schtasks, symlinks or encoding run on every OS. When unsure, a suite stays on all OSes.
- The macOS job runs only the suites that touch the OS. `install.sh` syntax and checkout detection run once, on `shell-macos`. Windows keeps its own Git Bash run.
- `concurrency` cancels superseded runs on pull requests only. Push, nightly and manual runs finish.
- Step names do not change: `lint/rule_audit.py` reads them.
- When a CI job nears its time cap, split the slowest suite's subject by family into its own job, and give the measured CI time before and after. This is a step of the `ci-hygiene` skill (owner, 2026-10-17 23:46 CDT).

Reason: a slow Windows runner failed a PR on tests its change did not touch. Fixed sleeps cost time, and macOS CI minutes went to suites
that do not touch the OS. A duplicate run costs minutes for no new verdict.

Accepted risk: a defect in an OS-independent suite that shows only on macOS or Windows is not caught. Unmeasured.

Kind: process
Home: .github/workflows/gates.yml
