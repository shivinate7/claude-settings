# Prose and code mix in one batch when that lands both sooner

## The ruling

The batch runner mixes prose lanes and code lanes in one batch when that lands both sooner. A prose lane that describes code not yet on main never merges ahead of that code. The same batch is fine.

Owner, 2026-11-13 11:19 and 11:24 CST, in runner 10 chat, relayed by the retrospective at 11:25 CST: prose and code stay in separate batches "when it's faster". His 2026-11-11 20:24 CST words (waiting-page item 521) were about merge order, not a wall.

Replaces two readings: "as their own batches" (retrospective) and "never share a batch" (coordinator, 2026-11-12 11:34 CST). Neither is a rule.

Outcome protected: main never says a thing that is not yet true. The mix is free, because one batch lands code and the prose that describes it together.

## Where it lives

- Skill `ci-hygiene`, step 8 (Batch lanes), points here for the mix.
- Roadmap ruling `prose-batch-order` (step `backlog-drain`) holds the owner's words. The plan reading is restart-plan 168159d3, 3.13.
- Decision `no-merge-during-batch-ci` keeps its own prose-only entry rule (`--express`). This record does not change it.
