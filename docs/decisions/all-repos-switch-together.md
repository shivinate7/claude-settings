# Degen and home switch to per-lane merge now; other child repos switch together

## The ruling

Owner ruling Q1 a (the cutover), 2026-11-12 09:42 CST, relayed by the coordinator at 09:50 CST: the per-lane merge target of R42 part 2 (`docs/plans/restart-plan.md`, entry R42) takes effect together. No repo switches alone, except as the next ruling says.

Owner ruling `own-degen-home-switch-now` (degen and home switch now), 2026-11-13 22:13 CST, is an exception to this decision. Degen and home switch to per-lane merge on the stable branch ahead of the drain. Every other child repo waits for the drain and switches together at the cutover.

The exception overrides ruling `own-act6-draft-prs-when-green` (child-repo draft PRs open once claude-settings main is green; the switch waits for the drain), for degen and home only.

State: target, not live, for every other child repo. Degen and home switch to per-lane merge on the stable branch now. The cutover lands with the removal act, act 4 of R42 part 2, which is a branch in progress.

- The merge tool is one shared script that every repo runs (`merge/merge.py`). A cutover in one repo gives that tool two rule sets. The exception accepts that for degen and home.
- Decision `uniform-over-variants` forbids one rule set per repo. Q1 a applies it to the cutover. The exception above is the one departure.
- Child repos read the stable branch (decision `stable-branch`) and fall back as decision `stable-fallback-warn` says. Both land before the cutover.
- Until the cutover, every repo except degen and home keeps its batch path, and a red main keeps the brake of decision `no-merge-onto-red-main`.

Why: act 4 changes the shared merge tool. Child repos would lose batching and get no stable branch or revert route if the cutover came first in one repo. Refuter, 2026-11-11 22:58 CST, gap 3.

Kind: process
Home: docs/decisions/uniform-over-variants.md
