# A pull request carries its review record on the PR

## The ruling

Owner, 2026-11-01 04:26 CST, waiting-page item 113 a. Source: the brief. The waiting page is not in this repo.

- Each PR carries a review record.
- The batch runner finds reviewed, green PRs itself.
- No merge message.

## The incident

- 2026-10-31 15:31 CDT. The auto-mode classifier refused a `send_message`. It handed banchi PR #1002 to the batch runner as "Merge Without Review".
- The refused act was a handoff, not an unreviewed merge.
- Unknown: what banchi names. In this repo, PR #1002 is idle-resume-compacts, merged at commit d39a0040. Unchecked whether they are the same PR.

## The form

The comment is the record. Its body:

```
<!-- review-record -->
PR: #<n>
Head: <40-hex sha>
Kind: normal|delete-only|docs-only
Guard or check: yes|no
Round <n>: <reviewer|design-reviewer>, <model>, <PASS|FAIL|PARTIAL>
Fix check: <40-hex reviewed head>, reviewer, <model>, <PASS|FAIL>
Net value: not owed|zero|positive|negative
CI: read live by merge --reviewed
```

- The first line is the marker. A line `---` after the CI line ends the record, so the attribution footer may follow.
- One `Round` line per reviewer. A round can hold more than one line.
- The `Fix check` line is optional, comes once after the Round lines, and is not a round (record `hold-unsafe-after-round-3`). `--fix-check HEAD:reviewer:MODEL:VERDICT` writes it. Its reviewed head must differ from Head. A FAIL is open. A PASS counts as its round passing when Guard or check is `no`, or Kind is `delete-only` and round 1 is its only round. A guard or check change owes round 3 whatever a fix check says. After round 3 it keeps the net value round 3 gave. With no round recorded it reads open.
- The comment never stores CI state. The merge tool reads CI live. `merge --reviewed` shows a draft
  PR as `CI draft, no run`, because a draft has no CI run.
- A body is not a record when the marker is missing, a field is malformed, round numbers skip, or a round is above 3.
- The newest record for a head counts. A record for an old head is stale.
- `merge <pr> --review-record --head <40-hex sha>` prints the body for the head the review read. When the PR's live head is another sha, it stops with exit 1 and prints no body, so a push after the review never relabels old rounds as current.
- A lane posts the body with the GitHub MCP comment tool after each round. `gh pr comment` uses GraphQL, which the cloud refuses (route graphql-gh-api-cloud).
- The one home of the form is the merge tool (`merge/merge.py`). `review_body` writes the body, `parse_review` reads it, and `review_state` gives each record's state. `reviewed_lines` prints the `--reviewed` list, `round_arg` reads `--round`, and `Host.review_comments` makes the one list read.

## The done rules

A change is done when one of these holds (rule `roles-review-cap-three`):

- Guard or check is `no` and round 1 or 2 is its last round. That round is PASS, or a fix check PASSes after its FAIL. The last `design-reviewer` line (across all rounds) is PASS or absent;
- Kind is `delete-only`, round 1 is its only round, and it is PASS or a fix check PASSes after its FAIL, with the same design line;
- round 3 is done, and Guard or check is `no`;
- round 3 is done, Guard or check is `yes`, and Net value is zero or positive;
- Kind is `delete-only`, Guard or check is `no`, and round 1 is done;
- Kind is `docs-only`, with zero rounds, unless the change is a record that files an owner ruling. That change posts `Kind: normal` with one round (decision `docs-only-prs-skip-review`).

- A last `design-reviewer` line of FAIL or PARTIAL keeps a record open on the PASS rule. The round 3 and `delete-only` done rules stay done, and their reason names the design failure.
- A round 3 verdict does not decide done. When Guard or check is `yes`, Net value does, even after a round 3 PASS: `not owed` is open, and `negative` holds the change (record `hold-unsafe-after-round-3`).
- A guard or check change owes round 3 whatever its earlier verdicts or a fix check say. Round 1 or 2 PASS reads open (owner item 359 pick b, 2026-11-07 14:41 CST: skip round 3 unless the change touches a guard or check, or round 2 failed).
- A `delete-only` change with Guard or check `yes` is done after a round 1 PASS, or after a round 1 FAIL and a fix check PASS. With a round 1 FAIL and no fix check PASS, or with a round 2, the normal path applies and round 3 is owed (decision `hold-unsafe-after-round-3`).
- `docs-only` with Guard or check `yes` is not a record: docs-only means no guard or check. The tool refuses it when it writes, and the parser rejects it.

## The cost

Counted as real `gh` calls, one call per list read however many pages it pages.

- `merge <pr> --confirm`, and the preview, add the round-3 check's one read, however many pages: the repo's issue comments since the oldest lane tip was committed (less a day for clock skew, the date from local git). A PR with no lane tips, or whose lane tips were unread, reads the comments since it opened. The check reads no open PR and no check run. Checking the PR's own head, the stale-record rule and the remedy text add no read.
- `merge --reviewed` makes two list calls per run. One lists the open PRs. The other lists the repo's issue comments since the oldest open PR, so it pages every comment of the repo since then, not only review records. The cost grows with the repo's comment traffic and with the age of the oldest open PR.
- Not a `gh` call: each `--reviewed` run also runs one `git fetch origin main` (`load_config`) and local git reads.
- Each ready PR that has a record adds three calls: the check runs, the commit statuses and the branch protection (required checks mode `protection`). A draft, and a PR with no record, add none.
- One ready PR with a record: five calls. With a pinned `merge.requiredChecks` list: also five, because the one protection compare moves to the start of the run and the per-PR protection read goes.
- `merge <pr> --review-record`: one PR read per call. `--fix-check` adds one paged read of the repo's issue comments since the PR opened. It writes nothing.
- No new long-lived process, file, cache or timer. The batch runner calls the list at each wake. A lane calls the render at each round.
- The test `ReviewedList` in `merge/test_merge.py` pins the two list reads and the five calls for one ready PR. The test `ReviewRoundCheckCost` pins the round-3 check's reads.

## The limits

- Kind, Guard or check, and docs-only are the lane's own claims. The tool does not check paths. It does not tell a record that files an owner ruling from other docs. Kind stays the lane's claim. Guards stop mistakes, not attackers (record `guard-guards-mistakes-only`).
- An integration PR usually has no record of its own. The round-3 check reads no open PR. It checks each lane tip of the batch and the PR's own head, and it matches each to a record by the record's Head line. A lane with no record passes (Q1).
- A push after a review makes the record stale. When a PR's newest record has Guard or check `yes`, and no record of that PR names a lane tip or the PR's own head, the check refuses: round 3 is owed on the new head. A stale record with Guard or check `no` passes. The check ties a record to a PR only by its comment. An unrelated PR's `yes` record, inside the comment window, can therefore refuse a batch that PR is not part of.
- When the dropped-lane read fails and `--undo-check-unknown-ok` lifts it, the lane tips are unread. The check still runs on the PR's own head, and prints that the lane tips were unread.
- The refusal's last line is its remedy, by state. A held change (Net value `negative`) is for the owner and gets no more rounds. Round 3 done with Net value `not owed` owes the net-value test. Below round 3, round 3 is owed.
- A `delete-only` change with Guard or check `no` and a round 1 FAIL reads done (rule `roles-review-cap-three`, the three-round review cap). The lane fixes the defect and posts a new review record for the new head, before the batch runner batches it. The fix push makes the old record stale.
- Unmeasured: whether the auto-mode classifier allows `merge --reviewed` and `merge <pr> --review-record`. Both are off `merge/cloud_allow.json`, which allows only `--confirm` and `--role`.
- One fix check per record. A second fix on a fixed head starts a new lane at round 1. `--fix-check` refuses unless its reviewed head equals the Head of the newest earlier record on the PR and that record has no Fix check line.

## Lane picks

The coordinator answered both at 23:14. Process-only.

- Q1. Should preview or confirm refuse a PR with no valid record? Pick a: no refusal for a missing record. Ruling 113 a names discovery only (rule `outcomes-grant-covers-named-act`). Since owner item 359 pick b, confirm refuses a lane whose newest record for its tip has Guard or check `yes` and is not done. Preview shows it as a `BLOCKED` line. A record that names the tip and does not parse refuses too. A failed read refuses unless `--undo-check-unknown-ok` gives a reason, as for the dropped-lane check. Not taken: confirm refuses a lane with no done record. Also not taken: preview prints a review line only.
- Q2. Which wins when a decision record and rule `roles-review-cap-three` disagree? Pick a: the rule outranks a decision record. Round 3 counts as done, whatever its verdict. Not taken: a final PASS is always needed. Record `standing-merge-grant` says so now.

Kind: process
Home: merge/merge.py
