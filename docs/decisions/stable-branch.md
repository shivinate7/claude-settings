# The stable branch moves only to a green main commit

## The ruling

Owner approved the design with the refuter's changes, 2026-11-12 09:48 CST, relayed by the coordinator at 09:50 CST. Under R42 part 2, sessions and installers run from a branch named `stable` on origin. A workflow run moves it after a green run of checks on main that covers the slow legs (changed by owner page item 880, 11:53 CST Nov 15). The move is fast-forward only.

State: target, not live. The mover is open pull request 2793. No `stable` branch is on origin yet.

- Trigger: `workflow_run` on the checks workflow's completion, for a run on main that ends in success and covers the slow legs. Two runs do: a `schedule` run (the daily), and a push run that the push skip proved (job `scope` skipped, job `push-skip` success). A Linux-only green push run moves nothing, and neither does a green manual (`workflow_dispatch`) run, since a manual run may not be the daily's head. Home of the check: `actions/stable-mover/run.sh`, decision `push-skip-on-proven-tree`.
- Move: fast-forward `stable` to that run's head sha. A move that is not a fast-forward is refused. The job never force-pushes.
- A red or cancelled run, and a green run that does not cover the slow legs, leave `stable` where it is.
- Installers and the merge tool read `stable`. Their fallback is decision `stable-fallback-warn`.

Why: a red main is never installed, because `stable` does not move onto it. Restart plan, entry R42 part 2.

Alternative not taken: a last job in the checks workflow, on push to main, in place of a separate workflow file. Refuter, 2026-11-11 22:58 CST, simpler route (b). The design names the `workflow_run` trigger. The owner approved the design in the ruling above.

Kind: process
Home: docs/plans/restart-plan.md
