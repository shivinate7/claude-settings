# Red CI after review round 3 is split, not a hole

## The question

What does a change do when its CI is still red after review round 3?

## The incident

None on record. The owner gave the ruling directly.

## The ruling

Owner ruling, 2026-10-13 14:50 CDT: "Split, then ask."

- Rounds 1 and 2 still fix the defect (rule `outcomes-tests-are-claims`).
- After round 3, red CI is not a named hole. Red CI is a failing claim.
- Split the change. Ship the part that passes. Open the red part as a new lane, with a fresh
  brief that records what failed. A held change (rule `roles-review-cap-three`) is the
  exception: it is parked, with no split and no new lane.
- The new lane starts at round 1, try 1.
- If no split is possible, or the failing test looks stale, bring it to the owner. Follow the
  stale-decision protocol (rule `outcomes-stale-decision-protocol`).
- Never merge it red. Never weaken a test to reach green.
- A red batch still drops the lane first (rule `git-integration-branch-merge`). The split
  happens in that lane's own fix.

## What protects it

GitHub required checks block a red merge: the branch's required-status-checks setting, mapped
as `git-never-merge-failing-ci`. No check enforces the split step.

Kind: process
Home: rule:roles-review-cap-three
