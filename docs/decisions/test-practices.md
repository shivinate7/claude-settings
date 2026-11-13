# Tests earn their keep by catching a real defect first

## The ruling

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

P3. A red counts only when an assert fails for the named cause; a crash, import error, timeout or "not built yet" is not a red. For a new feature, a crash on a missing name is not a red. After the build, the test-author makes a mutant of the built code on a scratch copy outside every repository, never on a repo file. It makes the copy without `.git`, such as with `git archive`, never a plain `cp -r`, and with no `.git` above it. It records the named case going red, reverts the mutant, and sends the result back to the orchestrator in its report.
- claude-settings decision mutation-report-scores-suites — "A crash is not a kill."
- mailaudit decision testing-mutant-dies-check-cause — a mutant "kill" came from an unrelated guard.
- claude-settings 06fe84c0b — the recorded red run was 14 AttributeErrors on missing symbols: it shows the test runs, not that it tells good code from bad.
Applies to: every test.

P4. Make each failure message name one cause.
- claude-settings 611140094 — the check reads the install log order; a red names the cause: "B started before A ended".
- banchi 8d6ab744 — the message reads "Expected >= 512, Received 180".
- claude-settings hooks/mutate_guard.py — a red on the wrong case reads WRONG CAUSE, not a kill.
Applies to: every test; guards and checks.

P5. A timed test is allowed, but first ask whether it is needed. A test whose verdict depends on elapsed time uses a synthetic clock, so machine load cannot change it. A hang guard, a wait cap that only stops a hung test, is a good use of a timed wait (owner, 2026-11-07 13:00 CST, for these three sentences). The rest is our reading, not the owner's words. A per-test or per-suite time limit is a hang guard too (coordinator pick, 2026-11-07 13:32 CST). A hang guard's cap sits well above the measured run. A test waits on a marker file or a condition, never a fixed sleep. A date, a time-zone offset or a DST switch is a real clock too. An assert never reads the real date or time-zone offset; inject the clock. A fixture stamped from the real clock, then judged by code that reads that clock again, uses one injected clock for both. A floor on a fixture's own delay is allowed: load only lengthens it.
- claude-settings plan c95-step2-escapes (roadmap branch) — 24 of 34 red runs on main were timing or load asserts.
- q_max b14be7a95 — a fixed wait went false-green under load.
- mailaudit 99bc9df — cases that waited real seconds moved to a virtual clock, asserts unchanged.
- joyous PR 68 — main went red on 2026-11-03 because a test read the real clock; the fix pins the tour test's clock.
- degen branch `l4-row-wait` — a test counted rows before they rendered; wait on the rendered condition, then count.
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

P10. A reviewer reads the recorded red run. If it is missing or in doubt, the reviewer makes a mutant on a scratch copy outside every repository and watches the named case go red (`roles-each-layer-proves-once`). It makes the copy without `.git`, such as with `git archive`, never a plain `cp -r`, and with no `.git` above it.
- q_max ac3397064 — a mutant stayed green because an earlier error response answered first.
- q_max decision D-804 — most round-2 mutants stayed green on the round-1 test file.
- claude-settings decision mutation-report-scores-suites — hand-written mutants that each name their case: 367 of 367 killed; sampled ast rates are upper bounds, not gold.
Applies to: review.

P11. A check enforces its rule's outcome, not a stricter or looser reading of it, so test the check on its rule's own cases, including the cases the rule allows.
- joyous PR 63 — the merge tool refused it while a ready batch that contained it ran CI. The owner ruled the refusal stricter than its rule, which only keeps main still under a running batch (2026-11-01 20:57 CST, relayed by the coordinator).
Applies to: guards and checks.

P2 (red on a named old commit) is held by lint/check_red_run.py (decision red-run-trailer-on-test-commits).

### Checks that could hold these (P7 not built)

- P5 (a verdict that depends on elapsed time uses a synthetic clock): built in part as lint/find_time_pinned.py, which lists sleep, elapsed-assert, test-cap and wait-cap. It lists no date or time-zone read as its own kind.
- P7 (scope first): a lint for an assert inside a conditional on the subject's presence, such as `if (await x.count())`.
- P3 (named cause): the mutation report already counts a crash as no kill (hooks/mutate_shared.py).

Kind: process
Home: agents/test-author.md
