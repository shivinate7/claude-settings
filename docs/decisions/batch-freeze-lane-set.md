# A batch's lane set freezes when its build starts

## The ruling

The batch runner freezes a batch's lane set when the build starts.

- A release or a drop that arrives after the build starts goes to the next batch. It never causes a rebuild. The one change after the freeze is the drop of a red run's blamed lane.
- The next batch builds and runs on top of the batch in CI. While its head holds the running batch's head, the merge brake lets the running batch merge (decision `no-merge-during-batch-ci`, the contains rule). A drop changes the running batch's head, so the next batch is built on the new head before that merge.
- A red run drops the one lane that blame names (one search per lane merge commit, pull request 2358), and any lane that depends on it, as step 8 already said. A lane red on form is dropped the same way, with no fix-and-re-merge. CI restarts at once. No lane that stays is linted again. Each lane was linted at hand-off and once at the join, before the build, and the batch head once, before ready.
- The batch is built as a draft. The batch-head lane lint runs, then the integration PR goes ready, with no rebuild between (decision `draft-until-reviewed`). A draft run skips every job, so a draft batch is never rebuilt only to close it.

Where it lives: step 8 (Batch lanes) of skill `ci-hygiene`, the batch runner's one home for this. No second copy.

Why: batch 66 merged nothing in 5.5 hours (Nov 8, 14:50-20:20 CST). Runner 8 rebuilt it 6 or more times (66 through 66l) whenever a late release, hold or drop arrived mid-build. Each build with its suites took about 10 minutes. It also linted every lane again after each red, about 14 minutes per lane lint (n=4). It never built on top of the batch in CI. These figures come from runner 8's report, relayed in the coordinator's brief. They are unmeasured by the session that wrote this record, which did not re-read the batch's runs.

Sources: owner, 2026-11-08 20:24 CST: "get the fix asap so we can lift asap". Owner, 2026-11-08 20:31 CST: "this fix needs to be mechanized". Both are quoted in the coordinator's brief for this lane. The four rules above are the coordinator's wording of the fix, from that brief.

Tool check: the merge tool enforces three parts of this freeze, and no more. It does not stop a hand edit of the branch or the PR body: the next `--batch-build` run rebuilds the branch from the block. `merge --batch-build NAME PR...` builds the integration branch `batch-NAME` as a draft and writes the frozen lane set into the integration PR body; a changed set is refused. `merge --batch-build NAME --ready` runs the one batch-head lane lint, then the repo's ready checks, then records the head that passed. It does not mark the integration PR ready: the tool sends no GraphQL, so it names the route, and the batch runner marks it. It lints again when the head moved since the last lint, even on a PR that is already ready. A FAIL of the lint or of a ready check stores each lane it names in the block (`Blamed:`). `merge --batch-build NAME --blame PR --run URL` stores the blame of a red CI run. It stores it only when the run is completed, failed, and on the batch PR's current head, and PR is a frozen lane. `merge --batch-drop NAME PR` takes off only a stored-blamed lane and its dependents, and refuses any other lane with the next batch as its route. A drop rebuilds `batch-NAME` from the frozen set and runs no lane lint. It asks the host to return a ready PR to draft. The tool sends no GraphQL, so the host cannot do that, and the head then needs `--ready` again. The owner's 20:31 CST ruling above put the check in the merge tool.

## One-time exceptions

- Owner, 2026-11-11 15:47 CST, in the batch runner's chat: "fold #2552, #2563 and #2597 (if it's released) into batch 82 as a one-time exception to batch-freeze-lane-set, rebuild under a new batch name, and re-run its local checks. #1099 waits for the next batch." Process-only, one time. The rebuilt batch is 82c. It holds pull requests 2588, 2593, 2594, 2552, 2563 and 2597. Pull request 2597 was released at 15:48 CST (coordinator, 2026-11-11 15:48 CST). This exception changes no rule above.

Kind: process
Home: skills/ci-hygiene/SKILL.md
