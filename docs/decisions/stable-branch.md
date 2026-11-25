# The stable branch follows each green push run of main

## The ruling

Under restart plan entry R42 part 2, sessions and installers run from a branch named `stable` on origin. Owner approved that design with the refuter's changes, 2026-11-12 09:48 CST, relayed by the coordinator at 09:50 CST.

Stable follows each green push run of main, for now. Owner, 12:59 CST Nov 16: "Just keep stable matching main for now then if that's easiest / Probably is easiest" and "Like keep that as a match every time main merges stable goes ahead too".

- Trigger: `workflow_run` on the checks workflow's completion, for a run on main that ends in success. Two events count: `push` and `schedule` (the daily). A manual (`workflow_dispatch`) run moves nothing, since a manual run may not be the daily's head. Home of the move: `actions/stable-mover/run.sh`.
- Move: fast-forward `stable` to that run's head sha. A move that is not a fast-forward is refused. The job never force-pushes.
- A red, cancelled or unknown run leaves `stable` where it is.
- A green push run covers the Linux fast jobs only (decision `push-skip-on-proven-tree`, which lets a push skip checks a passing PR run covered), so `stable` can sit on a commit whose Windows and mutation jobs have not run. The next daily covers them. The owner accepted this for now.
- Installers and the merge tool read `stable`. Their fallback is decision `stable-fallback-warn` (they fall back to main when stable is missing).

## Owner ruling: stay on stable, with a PR check

Owner, 14:27 CST Nov 25 2026, in the consultant's chat, on option "(b) Stay on stable + a PR check": "this is approved." The ruling:

- The merge tool keeps running from `stable`.
- A PR check runs stable's readers on the PR's tree, so a PR cannot put data on main that the installed tool refuses. The check is `lint/check_stable_readers.py`. Two steps in job `checks` run it: a fixture suite for the check, and the check itself on each pull request.
- The check fails when a stable reader refuses the tree, or reads it differently from the PR's own reader. It judges the records page only when the PR changed that page.
- Not yet landed: the guard and the merge tool refuse a stamp value they cannot read. Branch `guard-refuses-unknown-pin-string` carries it.
- The recovery switch `CLAUDE_SETTINGS_REF=main` stays. It makes installers read main, not `stable`.

Incident: PR #3863 (branch `confirm-needs-proof`) and PR #3871 (branch `lint-runs-listed-suites`) each put a stamp value on main together with its reader. Stable refused main's stamp until stable moved. Debt `old-merge-tool-refuses-stamp`: an old merge tool refuses main's `stamp.json`. <!-- glossary-ok: the debt's real id, as docs/records.md lists it -->

Cost per PR run, as measured: 2.8 s, or 7.8 s with the page proof (n=1 each). Four python starts, one more with the page proof.

Why: the owner wants `stable` to match main after each merge, which is the simplest rule. The mover moves `stable` on a push or daily run that ends with success, by fast-forward only, and reads no job of the run. So a red run never moves it, and a green run that skipped a suite does (see the green push run bullet above). Restart plan, entry R42 part 2.

Alternative not taken: a last job in the checks workflow, on push to main, in place of a separate workflow file. Refuter, 2026-11-11 22:58 CST, simpler route. The design names the `workflow_run` trigger. The owner approved the design in the first ruling above.

Kind: process
Home: docs/plans/restart-plan.md
