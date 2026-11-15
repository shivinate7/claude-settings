# The stable branch moves only to a green main commit

## The ruling

Owner approved the design with the refuter's changes, 2026-11-12 09:48 CST, relayed by the coordinator at 09:50 CST. Under R42 part 2, sessions and installers run from a branch named `stable` on origin. A workflow run moves it after a green push run of checks on main. The move is fast-forward only.

State: target, not live. The mover is open pull request 2793. No `stable` branch is on origin yet.

- Trigger: `workflow_run` on the checks workflow's completion, for a push run on main that ends in success.
- Move: fast-forward `stable` to that run's head sha. A move that is not a fast-forward is refused. The job never force-pushes.
- A red or cancelled push run leaves `stable` where it is.
- Installers and the merge tool read `stable`. Their fallback is decision `stable-fallback-warn`.

Why: a red main is never installed, because `stable` does not move onto it. Restart plan, entry R42 part 2.

Alternative not taken: a last job in the checks workflow, on push to main, in place of a separate workflow file. Refuter, 2026-11-11 22:58 CST, simpler route (b). The design names the `workflow_run` trigger. The owner approved the design in the ruling above.

Kind: process
Home: docs/plans/restart-plan.md
