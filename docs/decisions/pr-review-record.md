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
Fix check: <40-hex reviewed head>, reviewer, <model>, <PASS|FAIL|WIDE>
Net value: not owed|zero|positive|negative
CI: read live by merge --reviewed
```

- The first line is the marker. A line `---` after the CI line ends the record, so the attribution footer may follow.
- One `Round` line per reviewer. A round can hold more than one line.
- The `Fix check` line is optional, comes once after the Round lines, and a PASS is not a round (record `hold-unsafe-after-round-3`). `--fix-check HEAD:reviewer:MODEL:VERDICT` writes it. Its reviewed head must differ from Head. A PASS counts as its round passing in any round; with no round recorded it reads open. `--fix-check` also refuses, with exit 2 and no record, a record whose rounds fall below the round floor of the earlier records (see No reset), so a fix check reaches the last round of the record it follows; the floor reads only the round number and the slot a failed fix check fills. After the final round, every fix check keeps the net value, guard and kind of the newest earlier record that reached the final round, first or chained (that is the record it follows, unless a short record written before this check sits between), and `--fix-check` refuses a change with exit 2, no record, and a reason naming the field and both values. Before the final round the three may change. `--fix-check` also refuses, with exit 2 and no record, a record that lacks a Round line of the record it follows (the newest earlier record, or the `--fix-base-record` source): copy every Round line unchanged; extra lines are allowed. A plain `--review-record` with no `--fix-check` is floored where it is written too: it refuses, with exit 2 and no record, a record below the floor (see No reset).
- A FAIL is open until the next record. It counts as the next round, N+1: that record carries `Round N+1: reviewer, <model>, FAIL` and no Fix check line, so `--fix-check` may follow again. A FAIL that counts as round 3 makes that record a round-3 record. After round 3 a FAIL holds the change (owner item 356 a).
- A WIDE is open. Its fix starts a new lane at round 1.
- No reset: a round count never goes down on a PR. The floor is the highest last round over every earlier record that parses, plus 1 when that record has a Fix check FAIL. It is also plus 1 when that record's last round n is below 3 and holds a FAIL line, and no record from it on has a Fix check line. A newest record below the floor reads open, and the write step refuses it with "run round n+1". Why: on PR 1893 (lane record-claim-cites-code) three records each held only `Round 1: FAIL`, on three heads, so each reset the three-round cap (rule `roles-review-cap-three`; roadmap step `round-one-reset`, filed by triage 08:17 CST Nov 8). A fresh round 1 stays open after a Fix check line, after a failed fix check, and after round 3 (the coordinator's standing answer on step `fix-check-chain`). Why: `round <F> is the floor, set by head <9-hex>, but this record's last round is M`. A WIDE sets the floor at its own last round. A new lane is a new branch and PR, so it starts over.
- Counted slot: when an earlier record has a Fix check FAIL after round N, the round N+1 lines of every later record on the PR must include a FAIL line. Otherwise the PR reads open. Why: `the failed fix check fills round N+1`.
- The comment never stores CI state. The merge tool reads CI live. `merge --reviewed` shows a draft
  PR as `CI draft, no run`, because a draft has no CI run.
- A body is not a record when the marker is missing, a field is malformed, round numbers skip, or a round is above 3.
- The newest record for a head counts. A record for an old head is stale.
- `merge <pr> --review-record --head <40-hex sha>` prints the body for the head the review read. When the PR's live head is another sha, it stops with exit 1 and prints no body, so a push after the review never relabels old rounds as current. One exception: a record that reads open may name an ancestor of the live head. It has no Fix check line and every line of its last round is FAIL. One GitHub compare read proves the ancestor. A PASS record reads no compare. Why: on PR 1565 (export-page-cookie-linear) round 1 failed before the PR existed, and the fixes moved the head, so the FAIL record and the fix check after it could not be posted.
- A lane posts the body with the GitHub MCP comment tool after each round. `gh pr comment` uses GraphQL, which the cloud refuses (route graphql-gh-api-cloud).
- The one home of the form is the merge tool (`merge/merge.py`). `review_body` writes the body, `parse_review` reads it, and `review_state` gives each record's state. `reviewed_lines` prints the `--reviewed` list, `round_arg` reads `--round`, and `Host.review_comments` makes the one list read.

## The done rules

A change is done when one of these holds (rule `roles-review-cap-three`):

- round 1 or 2 is its last round, that round is PASS or a fix check PASSes after its FAIL, and the last `design-reviewer` line (across all rounds) is PASS or absent;
- round 3 is done (no FAIL or PARTIAL line at round 3), and Guard or check is `no`;
- round 3 is done (no FAIL or PARTIAL line at round 3), Guard or check is `yes`, and Net value is zero or positive;
- Kind is `delete-only`, Guard or check is `no`, and round 1 is done;
- Kind is `docs-only`, with zero rounds, unless the change is a record that files an owner ruling. That change posts `Kind: normal` with one round (decision `docs-only-prs-skip-review`).

- A last `design-reviewer` line of FAIL or PARTIAL keeps a record open on the PASS rule. The `delete-only` done rule stays done. Round 3 stays done unless a round 3 line is FAIL or PARTIAL, a design line included. The reason names the design failure.
- A round 3 FAIL or PARTIAL holds the change, so the record is open (owner items 356 a and 362 b, relayed by the coordinator). A passing fix check clears a round-3 hold (owner item 363 b, relayed by the coordinator), and then the round-3 done rules apply. Otherwise, when Guard or check is `yes`, Net value decides done, even after a round 3 PASS: `not owed` is open, and `negative` holds the change (record `hold-unsafe-after-round-3`).
- A `delete-only` change with Guard or check `yes` and a round 1 FAIL is open unless a fix check PASSes. The rule owes rounds 2 and 3 when round 1 finds a safety hole.
- `docs-only` with Guard or check `yes` is not a record: docs-only means no guard or check. The tool refuses it when it writes, and the parser rejects it.

## The cost

Counted as real `gh` calls, one call per list read however many pages it pages.

- `merge --reviewed` makes two list calls per run. One lists the open PRs. The other lists the repo's issue comments since the oldest open PR, so it pages every comment of the repo since then, not only review records. The cost grows with the repo's comment traffic and with the age of the oldest open PR.
- Not a `gh` call: each `--reviewed` run also runs one `git fetch origin main` (`load_config`) and local git reads.
- Each ready PR that has a record adds three calls: the check runs, the commit statuses and the branch protection (required checks mode `protection`). A draft, and a PR with no record, add none.
- One ready PR with a record: five calls. With a pinned `merge.requiredChecks` list: also five, because the one protection compare moves to the start of the run and the per-PR protection read goes.
- `merge <pr> --review-record`: one PR read per call. Each call, with or without `--fix-check`, adds one paged read of the repo's issue comments since the PR opened. It writes nothing.
- In `merge --reviewed`, the no-reset check reads the comment list that the list already reads. It adds zero gh calls there.
- No new long-lived process, file, cache or timer. The batch runner calls the list at each wake. A lane calls the render at each round.
- The test `ReviewedList` in `merge/test_merge.py` pins the two list reads and the five calls for one ready PR.

## The limits

- Kind, Guard or check, and docs-only are the lane's own claims. The tool does not check paths. It does not tell a record that files an owner ruling from other docs. Kind stays the lane's claim. Guards stop mistakes, not attackers (record `guard-guards-mistakes-only`).
- Open: an integration PR has no record of its own.
- A `delete-only` change with Guard or check `no` and a round 1 FAIL reads done (rule `roles-review-cap-three`, the three-round review cap). The lane fixes the defect and posts a new review record for the new head, before the batch runner batches it. The fix push makes the old record stale.
- Unmeasured: whether the auto-mode classifier allows `merge --reviewed` and `merge <pr> --review-record`. Both are off `merge/cloud_allow.json`, which allows only `--confirm` and `--role`.
- Fix checks chain after a PASS. This reverses "one fix check per record". Its ruling is owner rule `roles-review-cap-three`: "A small fix to a round's finding gets a fix check and merges on green". The coordinator relayed it as roadmap step `fix-check-chain`. A second small fix may follow a record whose Fix check PASSed, and counts no round slot. After the final round, every fix check keeps the record's net value, guard and kind (record `hold-unsafe-after-round-3`: a passing fix keeps the net value the final round gave), so no fix check turns a held change into a done one. A FAIL counts as the next round inside the three-round cap (owner item 347 a, 13:12 CST Nov 7, relayed by the coordinator), never as a return to round 1; the lane posts that round's record, and it has no Fix check line. A WIDE starts a new lane at round 1. `--fix-check` refuses when the newest earlier record on the PR has a FAIL or WIDE Fix check. After a PASS, the reviewed head must also be an ancestor of the live head, from one compare read: ahead, not behind. Why: on PR 1679 a second small fix forced a fresh round. The reviewed head must equal that record's Head, or differ from it by record or notes files only. Record or notes files are Markdown files in the record folders of `lint/layout.json`, the notes and todo files, and the generated records page. Legacy folder names count only in a repo that is not rolled out. One head must be an ancestor of the other. The files between them come from one GitHub compare read; a failed read, a rename out of a code path, or 300 or more files refuses. Why: on PR 1515 (verdict-pipe-masks-exit) a notes-only commit after round 2 became the record's Head, so the fix check could not be recorded. A PR with no record of its own may name a record on another PR of this repo with `--fix-base-record <comment URL>`. That record must be the newest on its PR and have no Fix check line: a chain never runs through `--fix-base-record` (the coordinator's standing answer, 23:35 CST Nov 7, not the owner's words). A source record with any Fix check line is refused, so a replacement PR whose predecessor carries a fix check takes a fresh round 1 on its whole diff, and then the rounds the done rules owe. A failed fix check counts as the next round on the PR that holds it (owner item 347 a, see above); that count does not move to a replacement PR. A source record with no Fix check line stands in for the newest earlier record, and its last round sets the round floor for the stand-in record. Why: on PRs 1541 and 1497 (notes-fix-report) a fresh PR held the reviewed commits, and the lane had to copy the round-3 record first.
- Four switches. Each is one module constant in `merge/merge.py`, set to its default. Their code lands in a builder lane, so the tool does not enforce them yet.
  - `ROUND3_PARTIAL_HOLDS = True`. Q3 is answered by owner page item 362 b, relayed by the coordinator (saved 2026-11-07 14:41 CST, not the owner's typed words): a round-3 PARTIAL holds the change too. False: only a FAIL line at round 3 holds.
  - `FIX_PASS_CLEARS_ROUND3_HOLD = True`. Q4 is answered by owner page item 363 b, relayed by the coordinator (same time, not the owner's typed words): a fix check that passes clears a round-3 hold. Then the round-3 done rules apply: guard `no` is done, and guard `yes` needs net value zero or positive. False: the hold stands.
  - `ROUND3_DESIGN_FAIL_HOLDS = True`. Question Q5, does a design-reviewer FAIL in round 3 hold? Answered: the coordinator picked a at 14:15 CST, so it holds. This is the coordinator's pick, not the owner's words. False: only a reviewer FAIL line in round 3 holds.
  - `FIX_FAIL_AFTER_ROUND3_HOLDS = True`. The coordinator agreed at 14:15 CST that a fix check FAIL after round 3 holds. This is the coordinator's agreement, not the owner's words. False: a fix FAIL after round 3 reads open with the fix-failed why.

## Lane picks

The coordinator answered both at 23:14. Process-only.

- Q1. Should preview or confirm refuse a PR with no valid record? Pick a: no refusal now. Ruling 113 a names discovery only (rule `outcomes-grant-covers-named-act`). Not taken: confirm refuses an integration PR when a lane tip has no done record. Also not taken: preview prints a review line only.
- Q2. Which wins when a decision record and rule `roles-review-cap-three` disagree? Pick a: the rule outranks a decision record. Round 3 counts as done unless it FAILs or is PARTIAL: a round-3 FAIL or PARTIAL holds the change (owner items 356 a and 362 b, relayed by the coordinator). A passing fix check clears that hold (item 363 b). Not taken: a final PASS is always needed. Record `standing-merge-grant` says so now.

Kind: process
Home: merge/merge.py
