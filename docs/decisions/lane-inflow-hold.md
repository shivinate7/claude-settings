# New lanes wait while reviewed work waits

## The ruling

The coordinator starts no new lane while reviewed PRs wait to merge. Lanes that land the fixes for idle PRs, for unarchived lanes and for draining the reviewed queue still start. Owner, 2026-11-07 21:42 CST, in chat, on page item 384 (lane-inflow-hold): "ill allow holding off on spawning new lanes but u shd still be able to spawn the lanes that will result in these fixes landing".

- Why: lanes finished faster than batches merged. The coordinator's scan at 21:35 CST read 215 claude-settings PRs with a PASS review record on the live head, 142 of them under 6 hours old. The scan parsed only the last round line, and the merge tool has not checked it. Recent batches held 1 to 5 lanes, 26 batch merges in about 45 hours (main's first-parent log, 2026-11-06 to 2026-11-08).
- Still started: a lane that lands the PR ledger (step pr-state-is-on-the-pr), the archive sweep, or a larger or faster batch; a lane that fixes a red check on main.
- Waits: every other ready step, the owner's older asks included. Rule `parallelism-keep-going` (start each queued item when a lane ends) yields to this ruling while it holds.
- Bandaid: the owner called a hold a bandaid (2026-11-07 21:44 CST). The cause was a coordinator line, "a guard or check change batches alone", which capped batches at one guard PR per CI run. It was withdrawn at 21:46 CST. The fix for the cause is step merge-follows-review.
- Ends: when the owner lifts it. Step pr-backlog-clear carries the queue count at each batch merge.

Kind: process
Home: docs/decisions/lane-inflow-hold.md
