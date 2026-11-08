# New lanes wait until the owner lifts the hold

## The ruling

The coordinator starts no new lane until the owner lifts the hold. Lanes that land the fixes for idle PRs, for unarchived lanes and for draining the reviewed queue still start. Owner, 2026-11-07 21:42 CST, in chat, on page item 384 (lane-inflow-hold): "ill allow holding off on spawning new lanes but u shd still be able to spawn the lanes that will result in these fixes landing".

- Why: lanes finished faster than batches merged. Main's first-parent log holds 26 batch merges in 44 h 22 min, 2026-11-06 01:08 CST to 2026-11-07 21:30 CST.
- Still started: a lane that lands the fix for idle PRs, for unarchived lanes, or for draining the reviewed queue.
- Waits: every other ready step. Rule `parallelism-keep-going` (start each queued item when a lane ends) yields to this ruling while it holds. Whether the owner's own queued asks wait is open as waiting item 387 (hold-covers-owner-asks).
- Bandaid: the owner called the hold options bandaids (2026-11-07 21:44 CST, waiting item 386). Runner 8 named the cause, relayed by the coordinator at 21:46 CST: a coordinator handoff line, "a guard or check change batches alone", put most done PRs one per batch. The coordinator withdrew it at 21:46 CST. The fix for the cause is open as waiting item 386 (merge-follows-review).
- Ends: when the owner lifts it.

Kind: process
Home: docs/decisions/lane-inflow-hold.md
