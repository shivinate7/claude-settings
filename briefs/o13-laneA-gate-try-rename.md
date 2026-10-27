# Brief: o13 lane A, the gate/try rename on current main (redo PR #639)

Repo: shivinate7/claude-settings, from main 92643977. One lane: builder (sonnet), then reviewer (sonnet). It changes a guard (hooks/guard.py, the third-round step-up), so it gets up to three review rounds and, after round 3, the net-value test.

## Ruling
shiv, Oct 26: yes to all nine groups in plans/o13-one-word-per-meaning.md (roadmap branch); the code is renamed too, so his words and the code match. A hook that refuses or asks is a guard; a lint, test or CI job is a check; a review and its fix is a round. Only Claude Code's own names stay.

## Task
PR #639 (branch claude/project-thread-x5hnku, head 0b9925f) did groups 1 and 9 but is 300+ commits behind main. Read its body for the full list. Redo it on a new branch from current main (do not force-push the old branch): file, record, anchor, identifier and message renames; gates.yml to checks.yml with job names gates* to checks*; rule kind gate to check; the guard accepting `Round 3 of 3` (and `Try 3 of 3` for 14 days, note try-marker-sunset). Pick up every new `gate` use that landed since #639. Merge origin/main into your branch again just before you report, since other lanes edit gates.yml.
Do not change branch protection or .github/stamp.json's required list on main; list the old and new required check names in the PR body, so the batch merge can switch them in one act.

## Failure classes
- A required check renamed in the workflow but not in .github/stamp.json, so merge.py waits forever.
- The guard: `Round 3 of 3` on Sonnet allowed (must refuse), or on Opus asked (must allow).
- A stub left at an old path that check_hook_stubs.py does not know.

## Check that proves it done
The guard cases red on main, green on the branch. lint/check_glossary.py passes. `python3 bin/ci-job checks --lint --base origin/main` (or its renamed form) and `bin/ste-changed origin/main` pass; name any step red on main too.

## Report
At most 15 lines: PR (draft), head, red run, green run, each review round's verdict, the old and new required check names. Close #639 as replaced. Send the green, reviewed head to the build advisor thread "Advise the claude-settings build (9)". Do not rebase onto main and do not merge.
