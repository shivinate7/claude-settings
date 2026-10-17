# Tests prove outcomes, run where their subject lives, and never fail on runner speed

## The ruling

A test must not fail on runner speed.

1. A skipped test reports SKIP with a count, never PASS. The fail-closed test list comes from the guard modules on disk.
2. No test waits on a fixed sleep or a wall-clock bound. A test uses a marker file, a ratio to a same-process baseline, or an injected
   clock. No test times a run on a local device. One test checks that the code follows a speed best practice, such as a count of calls
   or cache hits.
3. One shared set of fixtures: one git template, and one fake each for `gh`, `claude` and `xcrun`. The macOS job runs only the suites that
   touch the OS.
4. The pure-parse guard families run in one Python process. The cases that need a real hook process stay as subprocess cases.
5. A test stays only when it names the real failure it catches: a wrong allow or deny, lost work, a stuck merge, or a wrong record. A test
   that pins a known gap becomes a debt entry, not a test.
6. A merge of look-alike tests keeps one row for each item in a guard's list, each part of its pattern, and each filter. A row that alone
   fails when that item goes stays.
7. Each CI job runs only when a file that its suites read changes.

Reason: a slow Windows runner failed a PR on tests its change did not touch. Fixed sleeps cost time, and macOS CI minutes went to suites
that do not touch the OS.

Kind: process
Home: .github/workflows/gates.yml
