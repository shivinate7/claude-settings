# A batch's lane set freezes when its build starts

## The ruling

The batch runner freezes a batch's lane set when the build starts.

- A release or a drop that arrives after the build starts goes to the next batch. It never causes a rebuild.
- The next batch builds and runs on top of the batch in CI. Its head holds the running batch's head, so the merge brake does not refuse it (decision `no-merge-during-batch-ci`, the contains rule).
- A red run drops the one lane that blame names (one search per lane merge commit, pull request 2358). CI restarts at once. No lane that stays is linted again. Each lane was linted once, before the build, and the batch head once, before ready.
- The integration PR goes ready at the first build. A draft run skips every job, so a draft batch is never rebuilt only to close it.

Where it lives: step 8 (Batch lanes) of skill `ci-hygiene`, the batch runner's one home for this. No second copy.

Why: batch 66 merged nothing in 5.5 hours (Nov 8, 14:50-20:20 CST). Runner 8 rebuilt it 6 or more times (66 through 66l) whenever a late release, hold or drop arrived mid-build. Each build with its suites took about 10 minutes. It also linted every lane again after each red, about 14 minutes per lane lint (n=4). It never built on top of the batch in CI. Measured by the coordinator, in its brief for this lane; the batch's runs were not re-read here.

Sources: owner, 2026-11-08 20:24 CST, as relayed in the coordinator's brief: fix the cause before new lanes start. The four rules above are the coordinator's brief, not the owner's own words.

Tool check: no tool rebuilds or lints a lane set by itself. `merge --lane-lint` runs only when a session types it. The draft step (`merge <pr> --confirm` on a draft) runs the repo's ready checks once, before the ready mark, and never on a PR that is already ready. A drop runs neither. Nothing in `merge/` or `bin/` needs a change for this ruling.

Kind: process
Home: skills/ci-hygiene/SKILL.md
