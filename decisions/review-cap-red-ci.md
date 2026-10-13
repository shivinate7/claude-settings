# Red CI after review round 3 is split, not a hole

## The question

What does a change do when it still fails CI after review round 3?

## The incident

None on record. The owner gave the ruling directly.

## The ruling

Owner ruling, 2026-10-13 14:50 CDT: "Split, then ask."

- After round 3, a change known to fail CI is not a named hole. Red CI is a failing claim.
- Split the change. Ship the part that passes. Open the red part as a new lane, with a fresh
  brief that records what failed.
- If no split is possible, or the failing test looks stale, bring it to the owner. Follow the
  stale-decision protocol (rule `outcomes-stale-decision-protocol`).
- Never merge it red. Never weaken a test to reach green.

## What protects it

No check enforces the split step. The rule in CLAUDE.md states it. The merge rule that the PR
merges on green is the only other guard named there.

Kind: process
Home: rule:roles-review-cap-three
