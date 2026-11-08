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
- The `Fix check` line is optional, comes once after the Round lines, and a PASS is not a round (record `hold-unsafe-after-round-3`). `--fix-check HEAD:reviewer:MODEL:VERDICT` writes it. Its reviewed head must differ from Head. A PASS counts as its round passing in any round; with no round recorded it reads open. `--fix-check` also refuses, with exit 2 and no record, a record whose rounds fall below the round floor of the earlier records (see No reset). So a fix check reaches the last round of the record it follows. The floor reads only the round number and the slot a failed fix check fills. After the final round, every fix check, first or chained, keeps the net value, guard and kind of the newest earlier record that reached the final round. That is the record it follows, unless a short record written before this check sits between. `--fix-check` refuses a change with exit 2, no record, and a reason naming the field and both values. Before the final round the three may change. `--fix-check` also refuses, with exit 2 and no record, a record that lacks a Round line of the record it follows (the newest earlier record, or the `--fix-base-record` source): copy every Round line unchanged; extra lines are allowed. A plain `--review-record` with no `--fix-check` is floored where it is read, not where it is written.
- A FAIL is open until the next record. It counts as the next round, N+1: that record carries `Round N+1: reviewer, <model>, FAIL` and no Fix check line, so `--fix-check` may follow again. A FAIL that counts as round 3 makes that record a round-3 record. After round 3 a FAIL holds the change (owner item 356 a).
- A WIDE is open. Its fix starts a new lane at round 1.
- No reset: a round count never goes down on a PR. The floor is the highest last round over every earlier record that parses, plus 1 when that record has a Fix check FAIL before round 3. A newest record below the floor reads open. Why: `the record on head <9-hex> reached round <F>, so this record's last round <M> is below it; a new lane is a new pull request`, or, when the floor comes from a Fix check FAIL, `a failed fix check on head <9-hex> counts as round <F>, but this record's last round is <M>`. A WIDE sets the floor at its own last round. A new lane is a new branch and PR, so it starts over.
- Counted slot: when an earlier record has a Fix check FAIL after round N, the round N+1 lines of every later record on the PR must include a FAIL line. Otherwise the PR reads open. Why: `a failed fix check on head <9-hex> counts as round <N+1>, and only a FAIL line fills it, but this record's round <N+1> has none`.
- A failed round stays failed. For each earlier record that parses, take its last round N. Round N is uncleared when it has a FAIL or PARTIAL line, or the record has a Fix check FAIL or WIDE, and no Fix check PASS. That record or any later one must then reach a round above N, or carry a Fix check PASS. At round 3 only a Fix check PASS clears it. Otherwise the PR reads open, and the why names the earliest record at the highest such round: `round <N> on head <9-hex> is not passed, and no later record reaches round <N+1> or carries a fix check PASS`. At round 3 the why ends `and no later record carries a fix check PASS`. Zero new gh calls.
- A fix check PASS does not clear a design reviewer's FAIL or PARTIAL. This is the lane's reading, and it keeps main's design-reviewer rule. It is the one exception to the rule above, and it narrows item 363 b to code reviewers. A round-3 design-reviewer FAIL or PARTIAL with a fix PASS stays held. Why: `the design reviewer in round 3 is <FAIL|PARTIAL>, and a fix check PASS does not clear it, so the finding becomes a new lane at round 1`. In the failed-round rule above, a fix check PASS does not clear an earlier round with a design-reviewer FAIL or PARTIAL line, and the why ends `a fix check PASS does not clear the design reviewer`.
- The comment never stores CI state. The merge tool reads CI live. `merge --reviewed` shows a draft
  PR as `CI draft, no run`, because a draft has no CI run.
- A body is not a record when the marker is missing, a field is malformed, round numbers skip, or a round is above 3.
- The newest record for a head counts. A record for an old head is stale.
- `merge <pr> --review-record --head <40-hex sha>` prints the body for the head the review read. When the PR's live head is another sha, it stops with exit 1 and prints no body, so a push after the review never relabels old rounds as current. One exception: a record that reads open may name an ancestor of the live head. It has no Fix check line and every line of its last round is FAIL. One GitHub compare read proves the ancestor. A PASS record reads no compare. `merge --reviewed` lists that record as stale, because no review read the live head. Why: on PR 1565 (export-page-cookie-linear), round 1 failed before the PR existed. The fixes moved the head, so the FAIL record and the fix check after it could not be posted.
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
- A round 3 FAIL or PARTIAL holds the change, so the record is open (owner items 356 a and 362 b, relayed by the coordinator). A passing fix check clears a round-3 hold (owner item 363 b, relayed by the coordinator; not a design reviewer's line, see above), and then the round-3 done rules apply. Otherwise, when Guard or check is `yes`, Net value decides done, even after a round 3 PASS: `not owed` is open, and `negative` holds the change (record `hold-unsafe-after-round-3`).
- A `delete-only` change with Guard or check `yes` and a round 1 FAIL is open unless a fix check PASSes. The rule owes rounds 2 and 3 when round 1 finds a safety hole.
- `docs-only` with Guard or check `yes` is not a record: docs-only means no guard or check. The tool refuses it when it writes, and the parser rejects it.

## The cost

Counted as real `gh` calls, one call per page of a list read. Most reads fit one page of 100.

- `merge --reviewed` makes two list reads per run. One lists the open PRs. The other lists the repo's issue comments since the oldest open PR, so it pages every comment of the repo since then, not only review records. The cost grows with the repo's comment traffic and with the age of the oldest open PR.
- Not a `gh` call: each `--reviewed` run also runs one `git fetch origin main` (`load_config`) and local git reads.
- Each ready PR that has a record adds three reads: the check runs, the commit statuses and the branch protection (required checks mode `protection`). A draft, and a PR with no record, add none.
- One ready PR with a record: five calls. With a pinned `merge.requiredChecks` list: also five, because the one protection compare moves to the start of the run and the per-PR protection read goes.
- `merge <pr> --review-record`: one PR read per call. `--fix-check` adds one paged read of the repo's issue comments since the PR opened. It writes nothing.
- The no-reset check reads the comment list that `merge --reviewed` already reads. It adds zero gh calls.
- No new long-lived process, file, cache or timer. The batch runner calls the list at each wake. A lane calls the render at each round.
- The test `ReviewedList` in `merge/test_merge.py` pins the two list reads and the five calls for one ready PR.

## The limits

- Kind, Guard or check, and docs-only are the lane's own claims. The tool does not check paths. It does not tell a record that files an owner ruling from other docs. Kind stays the lane's claim. Guards stop mistakes, not attackers (record `guard-guards-mistakes-only`).
- Open: an integration PR has no record of its own.
- A `delete-only` change with Guard or check `no` and a round 1 FAIL reads done (rule `roles-review-cap-three`, the three-round review cap). The lane fixes the defect and posts a new review record for the new head, before the batch runner batches it. The fix push makes the old record stale.
- Unmeasured: whether the auto-mode classifier allows `merge --reviewed` and `merge <pr> --review-record`. Both are off `merge/cloud_allow.json`, which allows only `--confirm` and `--role`.
- Fix checks chain after a PASS, at most two per chain (owner page item 426 a, 10:19 CST Nov 8, step `fix-check-chain`). This replaces "one fix check per record" (owner, 2026-11-05 07:45 CST). A second small fix may follow a record whose Fix check PASSed, and counts no round slot. A third refuses (`FIX_CHAIN_CAP` in `merge/merge.py`): the next fix starts a fresh chain at round 1. Its records run up to the last round the PR reached, and the lower ones read open until then. A failed or WIDE fix check ends the chain. After the final round, every fix check keeps the record's net value, guard and kind (record `hold-unsafe-after-round-3`: a passing fix keeps the net value the final round gave). So no fix check turns a held change into a done one. A FAIL counts as the next round inside the three-round cap (owner item 347 a, 13:12 CST Nov 7, relayed by the coordinator), never as a return to round 1. The lane posts that round's record, with no Fix check line. A WIDE starts a new lane at round 1. When the newest earlier record on the PR has a FAIL or WIDE Fix check, `--fix-check` refuses. After the final round, a FAIL or WIDE Fix check on any earlier record refuses too, so a plain record posted after it cannot hide it. After a PASS, the reviewed head must also be an ancestor of the live head, from one compare read: ahead, not behind. Why: on PR 1679 a second small fix forced a fresh round. The reviewed head must equal that record's Head, or differ from it by record or notes files only. Record or notes files are Markdown files in the record folders of `lint/layout.json`, the notes and todo files, and the generated records page. Legacy folder names count only in a repo that is not rolled out. One head must be an ancestor of the other. The files between them come from one GitHub compare read; a failed read, a rename out of a code path, or 300 or more files refuses. Why: on PR 1515 (verdict-pipe-masks-exit) a notes-only commit after round 2 became the record's Head, so the fix check could not be recorded.
- A PR with no record of its own may name a record on another PR of this repo with `--fix-base-record <comment URL>`. The named record must be on this repo, parse, have a PR line that names its own PR, and be the newest record there. It stands in for the newest earlier record. Its last round sets the round floor.
  - Why (stand-in): on PRs 1541 and 1497 (notes-fix-report lane) a fresh PR held the reviewed commits, and the lane had to copy the round-3 record first.
  - A source with a FAIL or WIDE Fix check is refused (coordinator's standing answer, 23:35 CST Nov 7, not the owner's words). The new PR then takes a fresh round 1 on its whole diff, and then the rounds the done rules owe. A failed fix check counts as the next round on the PR that holds it (owner item 347 a); that count does not move to a replacement PR.
  - A source with a PASS Fix check is a carry. It stands in only when the fix base is the source Head, and the source Head and the new head hold the same tree (two GitHub tree reads). The source PR must also be closed or merged, or the new PR's body must say `replaces #N`.
  - A carry skips the ancestor check of a chained fix. Tree equality replaces it.
  - A carry refuses when the source PR's own chain already holds 2 passed fix checks (chain cap, owner page item 426 a).
  - On the new PR, a carried record counts as the full cap, so no fix check follows it. A fix check that starts from a stand-in with no Fix check line counts one link, or the full cap when its base and Head hold equal trees.
  - Why (carry): replacement PRs #2139 and #2140 (notes-fix-page lane) replaced the lane's earlier PRs #1581 and #2021 with identical trees to fix a commit message. They had to rerun rounds 1 to 3 on unchanged code (coordinator, 10:29 CST Nov 8; roadmap step `replacement-pr-carries-review`).
  - Cost: a carry costs one PR read, the comment-list reads, and two tree reads, four when the source chain starts at a stand-in; a plain stand-in costs one more comment-list read. The same-PR path adds two tree reads only when its chain's oldest record is a stand-in and the plain count allows the fix.
- Four switches. Each is one module constant in `merge/merge.py`, set to its default.
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
