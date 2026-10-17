# Tests prove outcomes, run where their subject lives, and never fail on runner speed

## Ruling

A test must not fail on runner speed. Four changes:

1. A skipped test reports SKIP with a count, never PASS. The fail-closed test list comes from the guard modules on disk.
2. No test waits on a fixed sleep or a wall-clock bound. A test uses a marker file, a ratio to a same-process baseline, or an injected clock.
3. One shared set of fixtures: one git template, and one fake each for `gh`, `claude` and `xcrun`. The macOS job runs only the suites that touch the OS.
4. The pure-parse guard families run in one Python process. The cases that need a real hook process stay as subprocess cases.

Rules for the work:

- Cut first. Merge duplicates second. Rewrite third. Make tests faster last.
- No effort goes into a test that a later step deletes.
- A test stays only when it names the real failure it catches: a wrong allow or deny, lost work, a stuck merge, or a wrong record.
- A test that pins a known gap becomes a debt entry, not a test.
- A merge of look-alike tests keeps one row for each item in a guard's list, each part of its pattern, and each filter. A row that alone fails when that item goes stays.
- Speed: one test checks that the code follows a speed best practice, such as a count of calls or cache hits. No test times a run on a local device, because device load makes the time vary. The 8 speed-only sweep mutants go.
- Each CI job runs only when a file that its suites read changes.

Reason: many guard cases each start a Python process, fixed sleeps cost time, some tests cannot fail, and macOS CI minutes go to suites that do not touch the OS. A slow Windows runner failed a PR on tests its change did not touch.

Kind: process
Home: .github/workflows/gates.yml
