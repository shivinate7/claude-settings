# Tests prove outcomes, run where their subject lives, and never fail on runner speed

## The question

Two blind audits of every test, on 2026-10-14, found slow and fragile tests, and tests that cannot fail. Which changes does the repo make, and in what order?

## Ruling

Owner ruling, 2026-10-14 17:14 CDT. Make all four changes from the first audit, and run a blind review of test value and test triggers. Owner, 2026-10-14 16:24 CDT: a test must not fail on runner speed.

1. A skipped test reports SKIP with a count, never PASS. The fail-closed test list comes from the guard modules on disk.
2. No test waits on a fixed sleep or a wall-clock bound. A test uses a marker file, a ratio to a same-process baseline, or an injected clock.
3. One shared set of fixtures: one git template, and one fake each for `gh`, `claude` and `xcrun`. The macOS job runs only the suites that touch the OS.
4. The pure-parse guard families run in one Python process. The cases that need a real hook process stay as subprocess cases.

Rules for the work:

- Cut first. Merge duplicates second. Rewrite third. Make tests faster last.
- No effort goes into a test that a later step deletes.
- A test stays only when it names the real failure it catches: a wrong allow or deny, lost work, a stuck merge, or a wrong record.
- A test that pins a known gap becomes a debt entry, not a test.
- A merge of look-alike tests keeps one row for each item in a guard's list, each part of its pattern, and each filter. A row that alone fails when that item goes stays. Owner, 2026-10-15 12:00 CDT.
- Speed: one test checks that the code follows a speed best practice, such as a count of calls or cache hits. No test times a run on a local device, because device load makes the time vary. The 8 speed-only sweep mutants go. Owner, 2026-10-15 12:40 CDT.
- Each CI job runs only when a file that its suites read changes.

Kind: process
Home: .github/workflows/gates.yml

## Why

The first audit counted about 2300 guard cases that each start a Python process, and about 81 cases that cannot fail. It counted about 195 s of fixed sleeps, and found that macOS uses most CI minutes on suites that do not touch the OS. The value review judged 1805 units: 73% keep, 18% merge, 4.5% cut, 4.3% rewrite. On 2026-10-14, slow Windows runners failed PR 432 twice, on two tests that its change did not touch.

Reports: `wt/test-audit-report/00-holistic.md` and `wt/test-value-report/00-holistic.md` on the owner's machine. They are working notes, not records.
