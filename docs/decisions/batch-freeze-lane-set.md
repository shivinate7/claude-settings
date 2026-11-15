# A batch's lane set freezes when its build starts

## The ruling

The batch runner freezes a batch's lane set when the build starts.

State: live until the cutover (decision `all-repos-switch-together`). After the cutover no batch is built, so this record is retired with the batches it governs.

- A release or a drop that arrives after the build starts goes to the next batch. It never causes a rebuild. The one change after the freeze is the drop of a red run's blamed lane.
- The next batch builds and runs on top of the batch in CI. While its head holds the running batch's head, the merge brake lets the running batch merge (decision `no-merge-during-batch-ci`, the contains rule). A drop changes the running batch's head, so the next batch is built on the new head before that merge.
- A red run drops the one lane that blame names (one search per lane merge commit, pull request 2358), and any lane that depends on it, as step 8 already said. A lane red on form is dropped the same way, with no fix-and-re-merge. CI restarts at once. No lane that stays is linted again. Each lane was linted at hand-off and once at the join, before the build, and the batch head once, before ready.
- The batch is built as a draft. The batch-head lane lint runs, then the integration PR goes ready, with no rebuild between (decision `draft-until-reviewed`). A draft run skips every job, so a draft batch is never rebuilt only to close it.

Where it lives: step 8 (Batch lanes) of skill `ci-hygiene`, under its until-the-cutover part, the batch runner's one home for this. No second copy.

Why: batch 66 merged nothing in 5.5 hours (Nov 8, 14:50-20:20 CST). Runner 8 rebuilt it 6 or more times (66 through 66l) whenever a late release, hold or drop arrived mid-build. Each build with its suites took about 10 minutes. It also linted every lane again after each red, about 14 minutes per lane lint (n=4). It never built on top of the batch in CI. These figures come from runner 8's report, relayed in the coordinator's brief. They are unmeasured by the session that wrote this record, which did not re-read the batch's runs.

Sources: owner, 2026-11-08 20:24 CST: "get the fix asap so we can lift asap". Owner, 2026-11-08 20:31 CST: "this fix needs to be mechanized". Both are quoted in the coordinator's brief for this lane. The four rules above are the coordinator's wording of the fix, from that brief.

Tool check: the merge tool no longer has `--batch-build` or `--batch-drop` (its usage names no batch to open or build; `merge/test_merge.py` pins both as unknown flags), so it enforces none of this freeze. The owner's 20:31 CST ruling above put the check in the merge tool; that check left with the batch route.

## One-time exceptions

- Owner, 2026-11-11 15:47 CST, in the batch runner's chat: "fold #2552, #2563 and #2597 (if it's released) into batch 82 as a one-time exception to batch-freeze-lane-set, rebuild under a new batch name, and re-run its local checks. #1099 waits for the next batch." Process-only, one time. The rebuilt batch is 82c. It holds pull requests 2588, 2593, 2594, 2552, 2563 and 2597. Pull request 2597 was released at 15:48 CST (coordinator, 2026-11-11 15:48 CST). This exception changes no rule above.

Kind: process
Home: skills/ci-hygiene/SKILL.md
