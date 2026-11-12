# Each act of R42 part 2 goes as its own express batch

## The ruling

Owner ruling R55 (how the acts of the R42 part 2 step merge), recorded 2026-11-12 15:27 CST: each act of that step goes to batch runner 10 as its own express batch. Batch runner 10 is the batch runner session of this step.

An express batch holds one act's pull request and no other lane's. The batch runner builds it, checks it and merges it alone.

State: target for the rest of this step. Other lanes still batch as decision `session-tiers` says.

- One act is one lane pull request. No other lane joins its batch.
- The batch runner merges it under the merge grant of decision `standing-merge-grant`.
- When act 4 lands and per-lane merges replace batches (decision `all-repos-switch-together`), this rule ends with the batches it covers.

Reason: none stated in the ruling.

Kind: process
Home: docs/decisions/session-tiers.md
