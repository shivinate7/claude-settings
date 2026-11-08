# New lanes wait while the owner's hold stands

## The ruling

The coordinator starts no new lane while the hold stands. Two kinds of lane still start: a lane that lands a queue fix, and a lane for an ask the owner made himself.

- Source of the hold: owner, 2026-11-07 21:42 CST, in chat, on page item 384 (lane-inflow-hold, should new lanes wait): "ill allow holding off on spawning new lanes but u shd still be able to spawn the lanes that will result in these fixes landing". He picked none of the item's limits (50, 20 or none), so the hold has no queue-size limit.
- Queue fixes: the coordinator reads "these fixes" as the queue fixes (a gap fix filed as a step). Page item 387 (hold-covers-owner-asks, do your own asks still start) put that reading to the owner.
- Owner asks: owner, 2026-11-07 22:24 CST, page item 387, pick a: "Your own asks still start".
- Why: lanes finished faster than batches merged. Main's first-parent log holds 26 batch merges in 44 h 22 min, 2026-11-06 01:08 CST to 2026-11-07 21:30 CST.
- Waits: every other ready step. Rule `parallelism-keep-going` (start each queued item the owner asked for when a lane ends) yields to this ruling while it holds.
- The cause: page item 386 (merge-follows-review, make merges keep pace with reviews) calls the hold a bandaid. The owner picked a, b and c there at 22:25 CST. Pick a is step merge-builds-batches (the merge tool builds each batch from PR state). Pick b is step findings-ride-in-lane (a lane's findings ride in its own PR). Pick c adds to step pr-state-is-on-the-pr (backlog counts in every report).
- Ends: the ruling names no end. It holds until the owner rules on it again.

Kind: process
Home: rule:parallelism-keep-going
