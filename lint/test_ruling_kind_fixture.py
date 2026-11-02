"""Fixture text for the ruling-kind cases: lint/test_check_ruling_kind.py and hooks/test_prose_judge.py.

PR_RECORD is PR #1028's record at the time of this lane, as fixture text. It holds two `Kind: process`
lines, so the lint refuses it. ONE_KIND_RECORD is the same text with the second Kind line folded away.
Its Home line stays, so the record has one Kind line and its Home path must exist (HOME_PATH). The
one-Kind form is derived here, never hand-edited.

Standard library only. Not a suite: the cases import it, and no runner lists it.
"""
PR_RECORD = """# Tests prove outcomes, run where their subject lives, and never fail on runner speed

## The ruling

A test must not fail on runner speed. CI runs a job only when its suites' files change, runs OS-independent suites on ubuntu only, and splits a near-cap job's slowest suite by family (a `ci-hygiene` step).

1. A skipped test reports SKIP with a count, never PASS. The fail-closed test list comes from the guard modules on disk.
2. No test times a run on a local device. Fixed sleeps and wall-clock bounds are in P5 (no sleep or clock in a test), in the section below. One test
   checks that the code follows a speed best practice, such as a count of calls or cache hits.
3. One shared set of fixtures: one git template, and one fake each for `gh`, `claude` and `xcrun`.
4. The pure-parse guard families run in one Python process. The cases that need a real hook process stay as subprocess cases.
5. A test stays only when it names the real failure it catches: a wrong allow or deny, lost work, a stuck merge, or a wrong record (P2, red run). A test that pins a known finding
   becomes a debt, not a test.
6. A merge of look-alike tests keeps one row for each item in a guard's list, each part of its pattern, and each filter. A row that alone
   fails when that item goes stays.

## How to write a test that earns its keep

Kind: process

A test must catch a real defect before the person meets it; a test that misses it, or fails with no defect, costs time and trust and catches nothing.

P1. Assert the outcome the person meets, not a proxy (a log string, source text, a script line); after a pull, assert the stored version advances, not payload equality.
- joyous 7f2f398 — a source-text assert replaced by a check of the built behaviour.
- mailaudit decision testing-pull-payload-eq-void — payload equality after a pull proves nothing; assert the stored version advances.
- degen 50149a79 — a source-text check passed while the simulator showed the cap never acted; the check was dropped.
Applies to: every test.

P2. Prove red first on a named old commit, with a green control beside it.
- q_max dc079516b — a layout test red on the old commit, green on the fix commit.
- Counter: mailaudit 8452a12 and 8e94d76 — green suites while real defects shipped; one was found in live use because no test reached the state.
- Counter: claude-settings d8c5ac166 — a check waited for a string the install never prints, so it could never go red.
Applies to: every test that adds or changes a case.

P3. A red counts only when an assert fails for the named cause; a crash, import error, timeout or "not built yet" is not a red. For a new feature, a crash on a missing name is not a red. After the build, the test-author makes a mutant of the built code and records the named case going red.
- claude-settings decision mutation-report-scores-suites — "A crash is not a kill."
- mailaudit decision testing-mutant-dies-check-cause — a mutant "kill" came from an unrelated guard.
- claude-settings 06fe84c0b — the recorded red run was 14 AttributeErrors on missing symbols: it shows the test runs, not that it tells good code from bad.
Applies to: every test.

P4. Make each failure message name one cause.
- claude-settings 611140094 — the check reads the install log order; a red names the cause: "B started before A ended".
- banchi 8d6ab744 — the message reads "Expected >= 512, Received 180".
- claude-settings hooks/mutate_guard.py — a red on the wrong case reads WRONG CAUSE, not a kill.
Applies to: every test; guards and checks.

P5. Never use a fixed sleep or a wall-clock wait bound; wait on a marker file or a condition. Never put a real clock or machine load in an assert; use an injected clock or a same-process ratio.
- claude-settings plan c95-step2-escapes (roadmap branch) — 24 of 34 red runs on main were timing or load asserts.
- q_max b14be7a95 — a fixed wait went false-green under load.
- mailaudit 99bc9df — cases that waited real seconds moved to a virtual clock, asserts unchanged.
Applies to: every test.

P6. Treat a flake as a defect report: find its cause and make it deterministic before you widen a bound.
- claude-settings 53dc1bd81 — a random macOS failure was a real race; over 2584 fake-clock pairs, old code reported a stall in 1212 and new code in 0.
- degen 9e42fe74 — a flake was a product race; the new case holds both threads and is red on every run.
- Counter: degen 53710605 — widened a flaky wait and named no cause (a bandaid).
Applies to: every test; CI runs.

P7. Assert the scope before the subject: prove the test reached the thing under test before you assert on it.
- banchi docs/agent-traps.md — a case guarded by `if (await bar.count())` never ran its assert, because the fixture never drew the control.
- banchi 661d266d — the scope answer is asserted non-empty first, so the second count is known entered.
- degen 6e016862 — asserts the files are clean before the mutation and that the mutation applied.
Applies to: UI and browser tests; any test with a probe or a branch on whether the subject is present.

P8. Build fixtures that reach the states real use reaches, the empty and full-size ones included, from real data where the repo has it.
- mailaudit 8e94d76 — every test booted a store with data; the empty-store defect was found in live use.
- mailaudit 2ebc855 — a real export exposed a parser gap that a pre-parsed fixture hid.
- degen 54fc11b0 — fixture sizes taken from a copy of real use.
Applies to: fixtures; every test that builds a store or a dataset.

P9. Delete or loosen a test only with proof that coverage holds: one mutant per removed case, red on what stays, and delete a test never shown to fail.
- q_max dafd0f11c — cases deleted, each with a mutant that turns the remaining check red.
- mailaudit ccc1454 — a case never shown to fail was deleted as unproven.
- Counter: joyous 29eb4e0 then da58dcf — an agent dropped a working test to fit a test count in its brief.
Applies to: every change that removes or loosens a test case.

P10. A reviewer reads the recorded red run; if it is missing or in doubt, it makes a mutant on a scratch copy and watches the named case go red (`roles-each-layer-proves-once`).
- q_max ac3397064 — a mutant stayed green because an earlier error response answered first.
- q_max decision D-804 — most round-2 mutants stayed green on the round-1 test file.
- claude-settings decision mutation-report-scores-suites — hand-written mutants that each name their case: 367 of 367 killed; sampled ast rates are upper bounds, not gold.
Applies to: review.

P11. A check enforces its rule's outcome, not a stricter or looser reading of it, so test the check on its rule's own cases, including the cases the rule allows.
- joyous PR 63 — the merge tool refused it while a ready batch that contained it ran CI. The owner ruled the refusal stricter than its rule, which only keeps main still under a running batch (2026-11-01 20:57 CST, relayed by the coordinator).
Applies to: guards and checks.

### Checks that could hold these (not built)

- P2 and P3 (red run, named cause): a commit lint. A commit that adds a test case carries a `Red-run:` line that names the old commit and the failing assert.
- P5 (no sleep or clock): a lint for wall-clock reads and fixed sleeps in test asserts (time.time, performance.now, Date.now, sleep).
- P7 (scope first): a lint for an assert inside a conditional on the subject's presence, such as `if (await x.count())`.
- P3 (named cause): the mutation report already counts a crash as no kill (hooks/mutate_shared.py).

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
Home: .github/workflows/checks.yml
"""


KIND_LINE = "Kind: process"
HOME_PATH = ".github/workflows/checks.yml"  # the record's Home path, a file on main
SECOND_KIND = "\nKind: process\nHome: " + HOME_PATH + "\n"  # the second Kind line and its Home line
assert PR_RECORD.count("\nKind: process\n") == 2 and PR_RECORD.count(SECOND_KIND) == 1, "fixture drift"

ONE_KIND_RECORD = PR_RECORD.replace(SECOND_KIND, "\nHome: " + HOME_PATH + "\n")
assert ONE_KIND_RECORD.count("\nKind: process\n") == 1, "one-Kind form drift"
