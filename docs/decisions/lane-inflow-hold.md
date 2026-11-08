# New lanes wait while the owner's hold stands

## The ruling

The coordinator starts no new lane while the hold stands, except the lanes that the owner's words below let start.

- The hold: owner, 2026-11-07 21:42 CST, in chat, on page item 384 (lane-inflow-hold, should new lanes wait): "ill allow holding off on spawning new lanes but u shd still be able to spawn the lanes that will result in these fixes landing". He picked none of the item's queue-size limits.
- Owner asks: owner, 2026-11-07 22:24 CST, page item 387 (hold-covers-owner-asks, do your own asks still start), pick a, whose option text reads: "A lane for an ask you made starts during the hold, as the queue-fix lanes do."
- Gap fixes: owner, 2026-11-08 06:11 CST, saved on the waiting page (its save comment in page thread 39498742-caad-4394-b043-13ab1619051c), page item 410 (hold-which-fixes-start, which fixes start a lane), pick a, whose option text reads: "Every fix for a found gap may start a lane".
- Waits: every other ready-not-started step. Rule `parallelism-keep-going` (start each queued item the owner asked for when a lane ends) yields to this ruling while it holds.
- Ends: owner, 2026-11-08 11:00 CST, page item 424 (lane-hold-end-trigger), pick none, his words: "as soon as we fix the underlying issue that caused piling up it immediately can be lifted". The cause is that reviewed PRs never reach a batch and drafts with no usable record get no send-back (audit, coordinator, 2026-11-08 10:29 CST). The hold ends when steps reviewed-batch-line-reads and reviewed-sends-back have both merged.

Kind: process
Home: rule:parallelism-keep-going
