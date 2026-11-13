# Ready express lanes share one express batch

## The ruling

Every express lane that is ready when a batch builds joins one express batch. That batch goes to main ahead of every other lane. An express lane does not run alone.

- An express lane is a reviewed merge-flow or CI-fix lane on the express list (ruling R55, with R67's kinds of fix).
- A red express lane drops out and reruns, as in a normal batch (decision `batch-freeze-lane-set`). The others merge.
- An express lane that turns ready after the build joins the next express batch.
- Ruling R55 parts 2 to 4 stand: a batch already in CI is cancelled for the express batch, then merges main in and reruns.
- The merge brake still holds for the express batch (decision `no-merge-during-batch-ci`).

Why: five express lanes (#2916, #2671, #2990, #2969, #2986) queued to run alone, one after another. That was about 4 hours of CI at 48 minutes a run (batch 107, one run), read 16:52 CST Nov 12 by the coordinator; unmeasured here.

Sources: owner, 2026-11-12 17:09 CST, page item 663, pick a, ruling R65. It replaces ruling R55 part 1's "its own batch" (owner picks, 13:19 and 13:21 CST Nov 12). Home pick: coordinator, 2026-11-13 12:46 CST, a new file so the rule survives the retirement of `no-merge-during-batch-ci`.

Kind: process
Home: skills/ci-hygiene/SKILL.md
