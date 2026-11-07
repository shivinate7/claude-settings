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
- Coordinator, 2026-11-07 13:41 CST: part 3 is split. 3a is the ready-steps change on branch `ready-steps-next-act`: ready and orphaned steps get one next act in `build.py`, plus a ready count. 3b comes after part 1 merges: `build.py` shows a PR's next act from `merge --reviewed --json`.
- Coordinator, 2026-11-07 13:53 CST: a draft with no record reads `lane round 1`. An integration PR labelled `batch` reads `batch run`.
- Coordinator, 2026-11-07 13:54 CST: `merge --lane-lint <pr> --integration` sets the `batch` label after a PASS only.
- Coordinator, 2026-11-07 14:40 CST: a completed or failed lane is not live. An idle or `review_ready` lane stays live.
- Coordinator, 2026-11-07 15:10 CST: design times use the delivery time, 12:33 CST.

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
- **F4. Trackers count presence as progress.** Decision `stalled-steps` counted an open PR as a live lane. On main, `skills/roadmap/build.py` counts any non-archived session as live (symbol `ARCHIVED_SESSION`) until ready-steps (3a) lands. So a `review_ready` lane hides its draft from the over-12-hour draft row. Related: roadmap step `triage-stale-ready-report` and #1082 (roadmap build upkeep).
- **F5. Lanes cannot find the batch runner.** The `list_sessions` tags filter returns "not currently available". Hand-offs routed through the coordinator. #1353 waited on that forward.
- **F6. Stacked or dirty PRs have no next act.** #1042 has a done review record. It is stacked on #919 and dirty (it cannot merge cleanly). It sits in no queue.

## How it works

One ledger. Home: `merge/merge.py`. It extends `merge --reviewed`. It adds no tool.

Each open PR gets exactly one next act. The tool reads it from GitHub alone. The first match wins:

- Done review record for the live head: `batch`.
- Review record open: `lane round n`, n the next round owed. A failed fix check: `lane round 1`.
- Review record stale, newest record has no Fix check line: fix check. Stale, it has one: new lane at round 1 (decision `pr-review-record`; rule `roles-review-cap-three`).
- Label `held`, `parked` or `replaced`, with a `Waits on: debt:<slug>` or `Waits on: page:<item id>` comment line: `waits on` that debt or item.
- Label `batch` on an integration PR: `batch run`. It counts against the batch limit, aged from the label's last `labeled` event.
- Based on, or stacked on, #N: blocked on #N.
- Draft with no record: `lane round 1`.
- None of these: `NO NEXT ACT` (red).

The ledger reads no pull request's CI state. A batch line is a done record for the live head. `merge --lane-lint` checks the join, and the integration PR's CI run checks the merge. Its one CI-side read is one page (50) of main's runs, judged per workflow, for the main-red hold.

Each next act has an age limit, in one constant, `PR_STATE_AGE_HOURS` in merge/merge.py. Every limit is unmeasured (coordinator pick A, 12:30 CST Nov 7); the coordinator measures the real ages after the label rollout. Batch is 24 h, a first guess at one batch cycle. Blocked on #N has no limit of its own and is red while #N is red. A next act over its limit is red.

A main-red hold shows on each batch line it holds.

The tool prints two numbers. Each one's target is 0:

- Longest wait from a done review record to now.
- Count of open PRs with no next act.

Readers:

- Batch runner, at each wake. Its queue is the ledger. The ledger replaces its private list.
- Triage, at each roadmap publish, from part 3b. `skills/roadmap/build.py` prints a `stalled pr:` line for each red PR. The line is red, like a stalled step. The Stop hook in `lint/report_guard.py` holds triage until each line is disposed. Triage disposes a `stalled pr:` line the way it disposes a stalled step (decision `stalled-steps`): it gives the PR a next act, or names it under Input Needed, which escalates it to the coordinator.
- Coordinator and batch runner reports carry the two numbers.
- Lane side, part 2: `lint/report_guard.py` refuses a lane's final report that claims a round PASS with no review record for the live head.

Build order. Part 3b starts only after part 1 merges. This record sets no other order.

1. The ledger in `merge/merge.py`. Lane `pr-state-is-on-the-pr` builds it. Its labels cover held, parked, replaced and batch. Its sweep is this ledger read.
2. The lane check in `lint/report_guard.py`.
3a. Ready and orphaned steps get one next act in `skills/roadmap/build.py`, plus a ready count. Branch `ready-steps-next-act`.
3b. After part 1 merges: `skills/roadmap/build.py` shows a PR's next act from `merge --reviewed --json`. It prints the `stalled pr:` line.
4. `lint/report_guard.py` checks the report's `Unstarted:` line against the ready list, the on-merge Deviations line, and the parser gaps on PR #1503. Per the 13:20 ruling, those gaps are fixed here, not filed as notes.

## The cost

Per rule `outcomes-mechanize-rules`:

- Process starts: none, except one `git ls-tree` of main's workflow files, when a batch line exists. Files written: none. Timers: none. Logs: none.
- How often: at each batch runner wake. From part 3b, at each roadmap publish. At each lane Stop, the lane check (part 2).
- Reads per `merge --reviewed` run, all from GitHub:
  - the open-PR list, and the repo's comments since the oldest open PR (one list each);
  - one `issues/<n>/events` list for each PR that reaches the hold rule with the `batch` label, or with a hold label and a valid `Waits on:` line;
  - when a batch line exists, one page (50) of main's runs. A run's jobs are read only when that run did not succeed, plus one more read for a clear candidate.
  - The count per run is not measured yet.
- Tests to write with the build, one per red: no review record; stale head; batch over its limit; hold with no item.

## Open

- Batch runner 8 activity from 2026-11-06 15:15 CST to 2026-11-07 05:00 CST: unknown.
- The q_max PRs were not sampled.
- Stale-record act: this record says `fix check`, or a new lane at round 1. `merge.py` reads any stale record as `lane round n`. Ruling needed: which one stands.
- `merge --reviewed --json` (part 3b's input) does not exist on `pr-state-is-on-the-pr`. Ruling needed: which part adds it.
- A `review_ready` lane stays live (14:40 ruling), so its draft still hides from the draft row after 3a. Unknown whether part 3b fixes that.
- Dated by: a change to how the batch runner reads its queue, or to the next-act read in `merge --reviewed`. Either change rewrites this record.

Kind: build
Plan: docs/decisions/pr-ledger.md#the-ruling (all)
Plan: docs/decisions/pr-ledger.md#how-it-works (all)
Home: merge/merge.py
Home: lint/report_guard.py
Home: skills/roadmap/build.py
