# Ready express lanes share one express batch

## The ruling

Express lanes that are ready at the same time go to main in one express batch, ahead of every other lane (ruling R65).

- An express lane is a reviewed lane on the express list: merge-flow and CI-fix lanes (ruling R55), every fix that tracks or lands work (R67 part 4), and two more express lanes (R67 part 5).
- A red express lane drops out and reruns, as in a normal batch (decision `batch-freeze-lane-set`). The others merge.
- An express lane that turns ready after the build joins the next express batch (the late-lane rule of skill `ci-hygiene` step 8; ruling R65 is silent on it).
- Ruling R55 parts 2 to 4 stand: a batch already in CI is cancelled for the express batch, then merges main in and reruns.
- The cancel (R55 part 2, above) is the one exception to "the next batch builds and runs on top of the one in CI" (skill `ci-hygiene` step 8). A lone express lane is its own express batch.
- The merge brake still holds for the express batch (decision `no-merge-during-batch-ci`).

Why: five express lanes (#2916, #2671, #2990, #2969, #2986) queued to run alone, one after another. That was about 4 hours of CI at 48 minutes a run (batch 107, one run), read 16:52 CST Nov 12 (ruling R65); unmeasured here.

Sources: owner, 2026-11-12 17:09 CST, page item 663, pick a, ruling R65. It replaced the own-batch wording of ruling R55 part 1, which now reads "the one express batch" (owner picks, 13:19 and 13:21 CST Nov 12). Home pick: coordinator message to lane express-batch-r65, 2026-11-13 12:46 CST (not yet in a record on main), a new file so the rule survives the retirement of `no-merge-during-batch-ci`.

Kind: process
Home: skills/ci-hygiene/SKILL.md
