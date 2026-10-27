# Brief: c77, brake a running lane at a full machine (finish PR #642)

Repo: shivinate7/claude-settings, from main 43d9af20. One lane: builder (sonnet), then reviewer (sonnet). This changes a guard, so it gets up to three review rounds and, after round 3, the net-value test.

## Ruling
shiv, waiting page item 30, Oct 27 11:45 CDT, option (a): non-blocking questions (PR #648, merged) plus the per-write disk check (PR #642), refusing only at a full machine (memory over 95%, or disk under the smaller of 5% and 5 GB), with a one-line exception in rule outcomes-mechanize-rules for background agents' own writes.

## Task
1. Bring PR #642 (branch claude/project-thread-rqwx3m, head 46a9060, 235 commits behind main) onto current main: a new branch from main with its diff re-applied (no force-push of the old branch). Keep its decision text, cases and proof shape; resolve any drift in hooks/guard.py and hooks/test_guard.py.
2. Add the one-line exception to CLAUDE.md, rule outcomes-mechanize-rules: a background agent's own write may read the machine load once inside the guard hook already running for it. Say its cost (one memory read and one statfs per subagent write, no process, no file, no timer) in decision machine-load-brake, and point both at each other.
3. PR body cites the ruling with its time.

## Failure classes
- The orchestrator's own writes braked (it is the session that frees the disk: verification-recovery-not-gated-on-own-state).
- A refusal at a busy, not full, machine (a guard that cries wolf).

## Check that proves it done
`GUARD_FAMILY=load-brake` cases: red against main's guard, green on the branch (the one cloud-container probe case red on main too is named, not counted). `python3 bin/ci-job gates --lint --base origin/main` and `bin/ste-changed origin/main` pass.

## Report
At most 15 lines: PR (draft), head, red run, green run, each review round's verdict. Close #642 as replaced. Send the green, reviewed head to the build advisor thread "Advise the claude-settings build (9)". Do not rebase onto main and do not merge.
