# c44 in the cloud: merged work leaves no worktrees behind

Cloud build thread brief. Build advisor, Oct 26, against claude-settings main 3f71d6b. Full step text:
briefs/c44-merged-work-cleans-up.md (lanes 1 to 3, first check, proof). Its "paste into a Windows
session" line no longer applies: build in the cloud, prove with fixture tests; shiv confirms on his
machines after merge.

## Order and bases

- Lanes 2 and 3 first (janitor/sweep.py lock rule; one sentence in the reports rule's home).
  Base: main.
- Lane 1 (merge/merge.py cleans its own worktree) edits merge.py, as do PR #577 (the pilot) and the
  c53 thread (merge.py on REST). Build lane 1 last, stacked on the c53 branch once it is pushed
  (ask the build advisor for its name), and say so in the PR body. If c53 has not pushed when lanes
  2 and 3 are done, open the PR with lanes 2 and 3 only and report lane 1 as waiting.

## First check

As the full brief says: if "the merge tool never removes worktrees" has a recorded reason, send it
to the build advisor before building lane 1.

## Roles

Orchestrate: test-author, builder, fresh reviewer (it changes what a deletion tool removes). PR stops
at green. Report: 25 lines max, Done, Deviations, Input Needed, Next.
