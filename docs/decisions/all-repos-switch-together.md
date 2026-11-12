# All repos switch to per-lane merges together

## The ruling

Owner ruling Q1 a (the cutover), 2026-11-12 09:42 CST, relayed by the coordinator at 09:50 CST: all repos switch together. The per-lane merge target of R42 part 2 (`docs/plans/restart-plan.md`, entry R42) takes effect in every repo together. No repo switches alone.

State: target, not live. Every repo still batches. The cutover lands with the removal act, act 4 of R42 part 2, which is a branch in progress.

- The merge tool is one shared script that every repo runs (`merge/merge.py`). A cutover in one repo would give that tool two rule sets.
- Decision `uniform-over-variants` forbids one rule set per repo. This ruling applies it to the cutover.
- Child repos read the stable branch (decision `stable-branch`) and fall back as decision `stable-fallback-warn` says. Both land before the cutover.
- Until the cutover, every repo keeps its batch path, and a red main keeps the brake of decision `no-merge-onto-red-main`.

Why: act 4 changes the shared merge tool. Child repos would lose batching and get no stable branch or revert route if the cutover came first in one repo. Refuter, 2026-11-11 22:58 CST, gap 3.

Kind: process
Home: docs/decisions/uniform-over-variants.md
