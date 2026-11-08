# New lanes wait while the owner's hold stands

## The ruling

The coordinator starts no new lane while the hold stands. A lane that lands the fixes that page item 384 (lane-inflow-hold, the hold on new lanes) names still starts. Owner, 2026-11-07 21:42 CST, in chat, on page item 384: "ill allow holding off on spawning new lanes but u shd still be able to spawn the lanes that will result in these fixes landing".

- Why: lanes finished faster than batches merged. Main's first-parent log holds 26 batch merges in 44 h 22 min, 2026-11-06 01:08 CST to 2026-11-07 21:30 CST.
- Still started: a lane that lands a fix that item 384 names; and a lane for a step the owner himself asked for (owner, 2026-11-07 22:24 CST, page item 387 (queue fixes and owner asks), pick a).
- Waits: every other ready step. Rule `parallelism-keep-going` (start each queued item when a lane ends) yields to this ruling while it holds.
- Bandaid: the owner called the hold options bandaids (2026-11-07 21:44 CST, page item 386 (the cause of the slow merges)). The fix for the cause is step merge-builds-batches (the merge tool builds each batch from PR state).
- Ends: the ruling names no end. It holds until the owner rules on it again.

Kind: process
Home: docs/decisions/lane-inflow-hold.md
