# Brief: c95 step 1b, measure which tests catch a planted bug

Repo: shivinate7/claude-settings, from current main. One lane: builder (sonnet), then reviewer (sonnet). Ruling: shiv, Oct 27 12:07 CDT, waiting page item 31, pick (e); his worry: whether the tests pin anything that matters (roadmap step c95).

## Task
hooks/mutate_guard.py and hooks/mutate_shared.py already mutate the guard (job gates-mutate-guard). Extend that one home, do not build a second mutation tool.
1. A report mode that runs the existing mutation engine over the other hooks and lint checks that decide a verdict (start with report_gate.py, feedback_gate.py, stall_watch.py, check_silent_undo.py; name any you add), and prints per file: mutants made, mutants killed, and the test files that killed none. Read on demand only; no timer, no new long-lived process; state its cost (runs, minutes) in the decision that owns mutation testing.
2. Run it once and write the per-file score table into that decision, with a gold-standard column (target: name it from the guard's own current kill rate).
3. List each test file that killed no mutant. Do not delete or change tests in this lane; each becomes a note or debt (rule roles-findings-are-debts-or-notes) for a later lane.

## Failure classes
- A mutant counted as killed because the test crashed for an unrelated reason (a throw is not a kill).
- A report that reads green when the engine could not run a file (must read unknown).

## Check that proves it done
A fixture with a test that pins nothing and one that catches a mutant: red on main (no report mode), green on the branch with the right verdicts, and an unrunnable file reported unknown. `python3 bin/ci-job gates --lint --base origin/main` and `bin/ste-changed origin/main` pass.

## Report
At most 15 lines: PR (draft), head, the score table's worst three files, the count of tests that killed nothing, review verdict. Send the green, reviewed head to the build advisor thread "Advise the claude-settings build (9)". Do not rebase onto main and do not merge.
