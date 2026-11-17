# The stable branch follows each green push run of main

## The ruling

Under R42 part 2, sessions and installers run from a branch named `stable` on origin. Owner approved that design with the refuter's changes, 2026-11-12 09:48 CST, relayed by the coordinator at 09:50 CST.

Stable follows each green push run of main, for now. Owner, 12:59 CST Nov 16: "Just keep stable matching main for now then if that's easiest / Probably is easiest" and "Like keep that as a match every time main merges stable goes ahead too". This replaces the earlier rule (owner page item 880, 11:53 CST Nov 15) that moved stable only on a run covering the slow legs.

- Trigger: `workflow_run` on the checks workflow's completion, for a run on main that ends in success. Two events count: `push` and `schedule` (the daily). A manual (`workflow_dispatch`) run moves nothing, since a manual run may not be the daily's head. Home of the check: `actions/stable-mover/run.sh`.
- Move: fast-forward `stable` to that run's head sha. A move that is not a fast-forward is refused. The job never force-pushes.
- A red, cancelled or unknown run leaves `stable` where it is.
- A green push run covers the Linux fast jobs only (decision `push-skip-on-proven-tree`), so `stable` can sit on a commit whose Windows and mutation jobs have not run. The next daily covers them. The owner accepted this for now.
- Installers and the merge tool read `stable`. Their fallback is decision `stable-fallback-warn`.

Why: the owner wants `stable` to match main after each merge, which is the simplest rule. A red main is still never installed, because `stable` does not move onto a red run. Restart plan, entry R42 part 2.

Alternative not taken: a last job in the checks workflow, on push to main, in place of a separate workflow file. Refuter, 2026-11-11 22:58 CST, simpler route (b). The design names the `workflow_run` trigger. The owner approved the design in the ruling above.

Kind: process
Home: docs/plans/restart-plan.md
