# Each act of R42 part 2 goes as its own express batch

## The ruling

Owner ruling R55 (how each act of R42 part 2, a merge-flow step, merges), 2026-11-12 13:21 CST. The coordinator relayed it to this lane at 13:22 CST, from plan commit 4fefc9f. Coordinator's relay, not the owner's words: "Each act, once review passes, goes to runner 10 with the words 'express R55' as its own express batch." Runner 10 is the batch runner session of this step.

docs/plans/restart-plan.md does not yet hold R55. Triage files it. Plan commit 4fefc9f adds R55 at `plans/restart-plan.md`. That entry also gives the owner's pick, "Express lane, and cancel a running batch for it too." The plan entry also says the act goes to main as its own batch, "ahead of every other lane." This record does not carry the cancel step yet.

An express batch holds one act's pull request and no other lane's. The batch runner builds it, checks it and merges it alone.

State: target for the rest of this step. Other lanes still batch as decision `session-tiers` says.

- One act is one lane pull request. No other lane joins its batch.
- The batch runner merges it under the merge grant of decision `standing-merge-grant`.
- When act 4 of R42 part 2 (the removal act) lands and per-lane merges replace batches (decision `all-repos-switch-together`), this rule ends with the batches it covers.

Reason: none stated in the ruling.

Kind: process
Home: docs/decisions/session-tiers.md
