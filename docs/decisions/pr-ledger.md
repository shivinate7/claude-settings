# Every open PR has one next act

## The question

Why did reviewed PRs sit idle, and what makes "passed review, then merged" hold?

## The ruling

Owner, 2026-11-07 12:22 CST, in chat to the coordinator. Quote:

> "the fact that PRs slipped everyone's radar itself despite us having them be part of our triage/status/plans/goals/handoffs means there's a mechanical failure here and you need to solve that"

Coordinator, 2026-11-07 12:33 CST: the proposal is accepted as written (the owner asked to solve it; it can be undone).

The intake rule rests on owner ruling 113 a (waiting-page item 113 a, 2026-11-01 04:26 CST, decision `pr-review-record`, a PR carries its review record on the PR): no merge message; the batch runner finds reviewed, green PRs itself. The coordinator's ruling:

- Intake is record-only. A PR joins a batch only through its review record.
- The batch runner batches from the review record, not from a message.
- A lane's message is a wake only.

Later coordinator rulings, Nov 7:

- Coordinator, 2026-11-07 13:20 CST: a gap gets fixed, not filed as a note.
- Coordinator, 2026-11-07 13:41 CST: part 3 is split. 3a is the ready-steps change on branch `ready-steps-next-act`: ready and stalled steps get one next act in `build.py`, plus a ready count. 3b comes after part 1 merges: `build.py` shows a PR's next act from `merge --reviewed --json`.
- Coordinator, 2026-11-07 13:53 CST: a draft with no record reads `lane round 1`. An integration PR labelled `batch` reads `batch run`.
- Coordinator, 2026-11-07 13:54 CST: `merge --lane-lint <pr> --integration` sets the `batch` label after a PASS only.
- Coordinator, 2026-11-07 14:40 CST: a lane whose status bucket is completed or failed is not live. Every other bucket stays live, `review_ready` included; an idle session status is live.
- Coordinator, 2026-11-07 15:10 CST: design times use the delivery time, 12:33 CST.
- Owner, 2026-11-10 14:07 CST, relayed by the coordinator at 14:08 CST: "i agree on letting it survive a clean merge where batch ci sees the problem rather than asecond review i agree it shd be mechanical tooo". The rule is in decision pr-review-record, The review a changed head owes.

## The evidence

Measured 2026-11-07 12:28 CST. "cs" is claude-settings. "q_max" is a second repo.

- 68 open cs PRs. 66 of them are drafts.
- 25 open q_max PRs.
- None of these PRs had landed.

Audit of 52 of them:

- 28 passed review and never reached a batch runner: 19 cs, 9 q_max.
- 15 never finished review.
- 6 wait on the owner.
- 3 are replaced or obsolete.

Failure points, each with its evidence:

- **F1. Lanes ended without the review record.** `merge --reviewed` at 12:27 CST found a review record on 3 of 67 open PRs: #919 (a review record for an old head), #1042 (lane `coordinator-acts`) and #1353 (a lane that waited on a forward). Six of eight sampled lanes sent PASS by message only: #1371, #1314, #1325, #1337, #1349 and #1363. #1371 has 0 comments. Nothing stops a lane from ending `review_ready` without its review record.
- **F2. The batch runner's queue was private.** It came from messages and lived only in batch runner 8's context (the runner's session label). Its heads went stale. #1371 was queued at commit 6086dc37 (the queued head). Its live head is commit 2d13d2bc. Its round 3 PASS covers the old head.
- **F3. A whole-queue hold had no age.** Waiting-page item 330 b (main red on a flaky test) held every merge from about 05:00 CST. PRs that change a guard or check went one per batch. No PR showed the hold.
- **F4. Trackers count presence as progress.** Decision `stalled-steps` counted an open PR as a live lane. `skills/roadmap/build.py` counted any non-archived session as live. After 3a, a completed or failed lane holds no step, and a `review_ready` lane still hides its draft from the over-12-hour draft row. Related: roadmap step `triage-stale-ready-report` and #1082 (roadmap build upkeep).
- **F5. Lanes cannot find the batch runner.** The `list_sessions` tags filter returns "not currently available". Hand-offs routed through the coordinator. #1353 waited on that forward.
- **F6. Stacked or dirty PRs have no next act.** #1042 has a done review record. It is stacked on #919 and dirty (it cannot merge cleanly). It sits in no queue.

## How it works

One ledger. Home: `merge/merge.py`. It extends `merge --reviewed`. It adds no tool.

Each open PR gets exactly one next act. The tool reads it from GitHub alone. The first match wins:

- Done review log for the live head, with a lane-lint PASS at that head: `batch`. Without the PASS: `lane lint`, owner the lane (coordinator pick, 12:01 CST Nov 12). A clean merge of main keeps a record for the live head (decision pr-review-record, The review a changed head owes). Not built.
- Review record open: `lane round n`, n the next round owed. A failed fix check: `lane round 1`.
- Review log stale, newest record has no Fix check line: fix check.
- Review log stale, newest record has a PASS Fix check, and the live head is a conflicted merge of main into the fixed head: one more fix verifier (decision pr-review-record). Its prior record must be a PASS that `review_state` accepts. Not built.
- Review log stale, in any other case: the fresh full review at the live head, as decision pr-review-record (The review a changed head owes) sets it.
- Label `held`, `parked` or `replaced`, with a `Waits on: debt:<slug>` or `Waits on: page:<item id>` comment line: `waits on` that debt or item. With no valid `Waits on:` line, the label holds nothing: no next act, shown red, even on a draft (lane pick, 12:13 CST Nov 12). This check runs after the stacked rule.
- Label `batch` on an integration PR: `batch run`. It counts against the batch limit, aged from the label's last `labeled` event.
- The PR's base ref names an open PR's head branch (#N): blocked on #N. A `Based on #N` body line does not stack (coordinator pick, 12:01 CST Nov 12, from review round 1).
- Draft with no record: `lane round 1`.
- None of these: no next act, shown red.

The first match wins, in this order. A held or unparseable record matches no record rule, so it falls to the label, blocked and draft rules. A stacked PR with a done record reads `batch`; the merge refuses one that cannot merge cleanly.

The ledger reads no pull request's CI state. A batch line is a done record for the live head. `merge --lane-lint` checks the join, and the integration PR's CI run checks the merge. Its CI-side reads are main's runs, judged per workflow, for the main-red hold.

Each next act has an age limit, in one constant, `PR_STATE_AGE_HOURS` in merge/merge.py. Lane round 2 to 4, fix check and fresh full review are 72 h, set from the record-to-record row of "The round-age measure" below (the coordinator's 72 h picks of 12:01 CST Nov 12 stand). That row does not split fix check from fresh full review. Batch is 24 h, from the last-record-to-merge row. Lane round 1 (72 h, aged from the PR's last update), batch run (24 h, aged from its label) and lane lint (72 h, lane pick 12:13 CST Nov 12) are unmeasured. `waits on` has no limit: a hold goes red when it has no page item or debt. Blocked on #N has no limit of its own and is red while #N is red. A next act over its limit is red. Red only prints (a flag on the `--reviewed` line); the join, the lane lint and the merge never read it, so today no limit cuts work off. Parts 3b and 4 will read red to hold triage, never a lane or a merge, and reopen this question when they land (owner, 12:54 CST Nov 12, item 595 note: a stored number is fine when it does not cut work off).

## The round-age measure

Measured 13:10 CST Nov 12, by REST (`gh api repos/shivinate7/claude-settings/...`, no GraphQL), on claude-settings only. Sample: every eighth PR from #1100 to #2860, plus all 351 open PRs: 524 PRs, 393 with a review log, created 2026-11-02 to 2026-11-12. A record's time is its comment's `created_at`.

| Age | Samples | Median | 90th | Max | Over the limit |
| --- | --- | --- | --- | --- | --- |
| PR opened to first record (no limit reads it) | 393 | 0.2 h | 2.1 h | 122.0 h | n/a |
| One record to the next (limit 72 h) | 709 | 0.6 h | 10.8 h | 56.8 h | 0 |
| Last record to merge (limit 24 h) | 47 | 7.8 h | 12.6 h | 22.3 h | 0 |

- No gap between two records passed 57 h. Of the 709 gaps, 217 add exactly one round (max 45.7 h; 363 add none, max 56.8 h), so 72 h flags no round that went on. Two PRs got their first record after 72 h (the longest 122 h). The opened-to-first-record row is context only; lane round 1 ages from the last update.
- Of 288 open PRs with a record, 100 are over 72 h since the newest record (max 118 h); of 63 open with no record, 23 are over 72 h since the last update. They are still open: they may yet get a round. They are the stalled PRs the ledger exists to show.
- 24 h for batch holds all 47 merged PRs that have a record, with 1.7 h to spare. The other 37 merged PRs in the sample have no record, so they are not measured. A main-red hold runs past it by design and shows red.
- A tighter limit would flag live work: 24 h on one record to the next flags 30 of 709.

A main-red hold shows on each batch line it holds.

The tool prints two numbers. Each one's target is 0:

- Longest wait from a done review record to now. It counts the acts `batch` and `lane lint`.
- Count of open PRs with no next act.

Readers:

- Batch runner, at each wake. Its queue is the ledger. The ledger replaces its private list.
- Triage, at each roadmap publish, from part 3b. `skills/roadmap/build.py` prints a `stalled pr:` line for each red PR. The line is red, like a stalled step. From part 4, the Stop hook in `lint/report_guard.py` holds triage until each line is disposed. Triage disposes a `stalled pr:` line the way it disposes a stalled step (decision `stalled-steps`): it gives the PR a next act, or names it under Input Needed, which escalates it to the coordinator.
- Coordinator and batch runner reports carry the two numbers.
- Lane side, part 2: `lint/report_guard.py` refuses a lane's final report that claims a round PASS with no review record for the live head.

Build order. Part 3b starts only after part 1 merges. This record sets no other order.

1. The ledger in `merge/merge.py`. Lane `pr-state-is-on-the-pr` builds it. Its labels cover held, parked, replaced and batch. Its sweep is this ledger read.
2. The lane check in `lint/report_guard.py`.
3a. Ready and stalled steps get one next act in `skills/roadmap/build.py`, plus a ready count. Branch `ready-steps-next-act`.
3b. After part 1 merges: `merge/merge.py` adds `--reviewed --json` and makes the stale-record act match this record. A held record on an old head falls through to the label rules, as above; part 1 tests stale first, so 3b fixes that order. The publisher runs it inside the read it already makes and passes the result in the live file. `skills/roadmap/build.py` shows each PR's next act and prints the `stalled pr:` line; it starts no process.
4. `lint/report_guard.py` checks the report's `Unstarted:` line against the ready list, the on-merge Deviations line, and the parser gaps on PR #1503. It also holds triage until each `stalled pr:` line is disposed, as it does for `stalled step:` lines. Per the 13:20 ruling, those gaps are fixed here, not filed as notes.

## The cost

Per rule `outcomes-mechanize-rules`:

- Process starts: one `gh api` call per read, and git starts for the checkout, a fetch of main, and reads of the config and main's workflow files (`git ls-tree` and `git show`). The git count grows with the number of workflow files and is not measured. Files written: none. Timers: none. Logs: none.
- How often: at each batch runner wake. From part 3b, at each roadmap publish. At each lane Stop, the lane check (part 2).
- Reads per `merge --reviewed` run, all from GitHub:
  - the open-PR list, and the repo's comments since the oldest open PR (one list each);
  - one `issues/<n>/events` list for each PR that reaches the hold rule with the `batch` label, or with a hold label and a valid `Waits on:` line;
  - when a batch line exists, one page (50) of main's runs. A run's jobs are read only when that run did not succeed, plus, for each candidate run it examines, its jobs and, unless the red already stands, its workflow file.
  - for each open PR whose newest record is stale, the clean-merge survival check's reads (decision pr-review-record, the cost): one `gh` commit read per commit walked, plus one compare per merge commit, local `git` starts, and at most one `git fetch origin` a run. The merge-tree writes objects to the object store.
  - The count per run is not measured yet.
- Reads per lane Stop (part 2): none unless the final report claims a round PASS. Then two `gh api` reads per claimed PR: the PR's head and its comments. A stale newest record adds the survival check's reads, the same as above.
- Tests to write with the build, one per red: no review record; stale head; batch over its limit; hold with no item.

## Open

- Batch runner 8 activity from 2026-11-06 15:15 CST to 2026-11-07 05:00 CST: unknown.
- The q_max PRs were not sampled.
- The round-age measure does not split fix check from fresh full review: both sit in the record-to-record gaps. Lane lint ages are not measured. Dated by: ten days of one repo; remeasure after a change to the round rules.
- A `review_ready` lane stays live (14:40 ruling), so its draft hides from the draft row. Unknown whether part 3b's `stalled pr:` line covers it.
- Dated by: a change to how the batch runner reads its queue, or to the next-act read in `merge --reviewed`. Either change rewrites this record.

Kind: build
Plan: docs/decisions/pr-ledger.md#the-ruling (all)
Plan: docs/decisions/pr-ledger.md#how-it-works (all)
Home: merge/merge.py
Home: lint/report_guard.py
Home: skills/roadmap/build.py
