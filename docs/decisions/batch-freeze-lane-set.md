# A batch's lane set freezes when its build starts

## The ruling

The batch runner freezes a batch's lane set when the build starts.

- A release or a drop that arrives after the build starts goes to the next batch. It never causes a rebuild. The one change after the freeze is the drop of a red run's blamed lane.
- The next batch builds and runs on top of the batch in CI. While its head holds the running batch's head, the merge brake lets the running batch merge (decision `no-merge-during-batch-ci`, the contains rule). A drop changes the running batch's head, so the next batch is built on the new head before that merge.
- A red run drops the one lane that blame names (one search per lane merge commit, pull request 2358), and any lane that depends on it, as step 8 already said. A lane red on form is dropped the same way, with no fix-and-re-merge. CI restarts at once. No lane that stays is linted again. Each lane was linted at hand-off and once at the join, before the build, and the batch head once, before ready.
- The batch is built as a draft. The batch-head lane lint runs, then the integration PR goes ready, with no rebuild between (decision `draft-until-reviewed`). A draft run skips every job, so a draft batch is never rebuilt only to close it.

- A lane's push to its own branch is refused while an open, ready pull request on the default branch holds that branch's remote tip in its head. A moved head breaks the batch's confirm (guard rule `push-batch-held`, step `lane-push-frozen-in-batch`). The tip is the clone's `refs/remotes/origin/<branch>`. The refusal wins over the agent-branch ask. Its remedy is to wait for the batch to merge or drop the lane. New work goes in a new lane. A list or compare that cannot be read allows the push and logs `push-batch-unread`. A forced push, a push that moves nothing and a lane with no remote tip are not judged here.
  - Cost: per non-forced push to a branch other than main or master, one local read of the tip, and a second of the source when the tip exists. Only a push that moves a tip reads GitHub: one open-list call per 100 rows, then one compare per ready pull request on the base. No call for a push of main, a dry run or a read verb. No process starts, no file written, no timer.

Where it lives: step 8 (Batch lanes) of skill `ci-hygiene`, the batch runner's one home for this. No second copy.

Why: batch 66 merged nothing in 5.5 hours (Nov 8, 14:50-20:20 CST). Runner 8 rebuilt it 6 or more times (66 through 66l) whenever a late release, hold or drop arrived mid-build. Each build with its suites took about 10 minutes. It also linted every lane again after each red, about 14 minutes per lane lint (n=4). It never built on top of the batch in CI. These figures come from runner 8's report, relayed in the coordinator's brief. They are unmeasured by the session that wrote this record, which did not re-read the batch's runs.

Sources: owner, 2026-11-08 20:24 CST: "get the fix asap so we can lift asap". Owner, 2026-11-08 20:31 CST: "this fix needs to be mechanized". Both are quoted in the coordinator's brief for this lane. The four rules above are the coordinator's wording of the fix, from that brief.

Tool check: no tool rebuilds or lints a lane set by itself. `merge --lane-lint` runs only when a session types it. The draft step (`merge <pr> --confirm` on a draft) runs the repo's ready checks once, before the ready mark, and never on a PR that is already ready. A drop runs neither. So the freeze is held by hand today. The owner's 20:31 CST ruling above puts the check in the merge tool. That is step `batch-freeze-lane-set-enforce`, a separate lane, not built here. Until it lands, the batch runner holds the freeze by hand.

Kind: process
Home: skills/ci-hygiene/SKILL.md
