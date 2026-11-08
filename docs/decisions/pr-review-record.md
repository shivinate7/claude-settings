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
Findings: none | <n>, this PR | <n>, follow-up #<pr>[, ...]
Net value: not owed|zero|positive|negative
CI: read live by merge --reviewed
```

- The first line is the marker. A line `---` after the CI line ends the record, so the attribution footer may follow.
- One `Round` line per reviewer. A round can hold more than one line.
- The `Fix check` line is optional, comes once after the Round lines, and is not a round (record `hold-unsafe-after-round-3`). `--fix-check HEAD:reviewer:MODEL:VERDICT` writes it. Its reviewed head must differ from Head. A FAIL is open. A PASS counts as its round passing in any round; after round 3 it keeps the net value round 3 gave; with no round recorded it reads open.
- `Findings` comes once, after the Fix check line and before Net value. `none` has nothing to file. `<n>, this PR` files `<n>` review findings in the lane's own PR. `<n>, follow-up #<pr>[, ...]` files them in follow-up PRs, one per topic (owner item 386 b, 2026-11-07 22:25 CST: a lane's review findings ride in its own PR, or in one follow-up PR per topic, never one PR or step per finding). `--review-record` needs `--findings`. A record with no Findings line is legacy only if created before the cut-off in the done rules.
- The comment never stores CI state. `merge --reviewed` reads no CI per PR. It reads the base's latest run once, when a batch line exists. The form's CI line keeps its old wording, because posted records carry it (`REVIEW_CI_LINE` in `merge/merge.py`).
- A body is not a record when the marker is missing, a field is malformed, round numbers skip, or a round is above 3.
- The newest record for a head counts. A record for an old head is stale.
- `merge <pr> --review-record --head <40-hex sha>` prints the body for the head the review read. When the PR's live head is another sha, it stops with exit 1 and prints no body, so a push after the review never relabels old rounds as current.
- A lane posts the body with the GitHub MCP comment tool after each round. `gh pr comment` uses GraphQL, which the cloud refuses (route graphql-gh-api-cloud).
- The one home of the form is the merge tool (`merge/merge.py`). `review_body` writes the body, `parse_review` reads it, and `review_state` gives each record's state. `reviewed_lines` builds the `--reviewed` ledger: one next act per open PR, with its age limit in `merge/merge.py` `PR_STATE_AGE_HOURS` (design: the PR ledger, record `pr-ledger`, draft PR #1419). `round_arg` reads `--round`. `Host.issue_comments` makes the one comment list read, which `reviewed_lines` and `Host.review_comments` (`--fix-check`) both use.

## The done rules

A change is done when one of these holds (rule `roles-review-cap-three`):

- round 1 or 2 is its last round, that round is PASS or a fix check PASSes after its FAIL, and the last `design-reviewer` line (across all rounds) is PASS or absent;
- round 3 is done, and Guard or check is `no`;
- round 3 is done, Guard or check is `yes`, and Net value is zero or positive;
- Kind is `delete-only`, Guard or check is `no`, and round 1 is done;
- Kind is `docs-only`, with zero rounds, unless the change is a record that files an owner ruling. That change posts `Kind: normal` with one round (decision `docs-only-prs-skip-review`).

- A last `design-reviewer` line of FAIL or PARTIAL keeps a record open on the PASS rule. The round 3 and `delete-only` done rules stay done, and their reason names the design failure.
- A round 3 verdict does not decide done. When Guard or check is `yes`, Net value does, even after a round 3 PASS: `not owed` is open, and `negative` holds the change (record `hold-unsafe-after-round-3`).
- A `delete-only` change with Guard or check `yes` and a round 1 FAIL is open unless a fix check PASSes. The rule owes rounds 2 and 3 when round 1 finds a safety hole.
- `docs-only` with Guard or check `yes` is not a record: docs-only means no guard or check. The tool refuses it when it writes, and the parser rejects it.
- A record with a Findings line is done only if its Findings check also passes. The check runs only on a record that the rules above call done.
  - `none` passes with no read.
  - `<n>, this PR` passes when the PR adds a file under the repo's debt store (its layout's `debts` folder and notes file), or adds lines to that notes file. Deleting a notes line does not count.
  - `<n>, follow-up #<pr>[, ...]` passes when each named PR is open or merged. A closed PR that was not merged does not pass. This PR does not pass.
  - A check that cannot read its input fails (owner, 2026-11-06 12:39 CST, page item 276 (unknown-read-one-rule), pick a). A follow-up PR that 404s is not done, and the line names it. Any other read failure is unknown, and it holds the record. `--findings-unknown-ok "<reason>"` lifts that hold, and the tool prints the lift.
  - A layout that cannot be read makes the record `findings unknown`. It holds the record, like other unknowns (owner item 276 a, 2026-11-06 12:39 CST).
  - Owner item 394 a, 2026-11-08 06:08 CST: a fix check may pass a push that only files this PR's findings (record `hold-unsafe-after-round-3`). The fix-check reviewer judges that push; it passes only when the reviewed record's Findings is `<n>, this PR`. The tool does not check it.
- The cut-off is `FINDINGS_REQUIRED_FROM` (merge/merge.py), the moment `--findings` reached main. It is never earlier than owner item 386 b's ruling time (2026-11-07 22:25 CST). A record with no Findings line, created at or after the cut-off, is not done. `merge --reviewed` reads it as `lane: review record lacks Findings`, at the lane round age limit. A record created before the cut-off keeps its legacy verdict.

## The cost

Counted as real `gh` calls, one call per page of a list read. Most reads fit one page of 100.

- `merge --reviewed` reads the open PRs (one call per page) and the repo's issue comments since the oldest open PR (one call per page, every comment, not only review records). It reads one `issues/<n>/events` list per PR that reaches the hold rule. When a batch line exists, it reads one page of the base's `actions/runs`. For a run that did not succeed, it also reads that run's jobs, and the jobs and workflow files of runs that may clear it. `Host.base_state` in merge/merge.py holds that count. It reads no head and no check run. The comment list grows with the repo's comment traffic and with the age of the oldest open PR.
- Each `--reviewed` run also runs one `git fetch origin main` (`load_config`) and local git reads. With no `.github/stamp.json` on main, `load_config` adds one `gh api` repo read.
- One ready PR with a record (a batch line), each list on one page, on a base with no run that did not succeed: three calls, the open PRs, the comments and the base's runs. With a pinned `merge.requiredChecks` list, four: one branch protection read at the start of the run compares the pin. A held PR adds one events read.
- `merge <pr> --review-record`: one PR read per call. `--fix-check` adds one paged read of the repo's issue comments since the PR opened.
- A Findings line reads only on a record the rules above call done: one paged read of the PR's files for `<n>, this PR` (one call per page), with a few local layout-file reads (no process, no writes), and one read per follow-up PR named. `none` costs what a legacy record costs.
- No new long-lived process, file, cache or timer. The batch runner calls the list at each wake. A lane calls the render at each round.
- The test `ReviewedList.test_one_ready_pr_with_a_record_costs_three_gh_calls` in `merge/test_merge.py` pins the three calls. `ReviewedLedger.test_reads_one_comment_list_no_head_and_at_most_one_event_list_per_held_pr` pins the list reads. `ReviewedList.test_findings_this_pr_with_a_debt_file_added_is_done_and_reads_its_files_once`, `ReviewedList.test_findings_follow_up_reads_each_named_pr_once` and `ReviewedList.test_findings_none_reads_no_more_than_a_legacy_record` pin the Findings reads. `ReviewFixFiling` pins that a filing push (and a filing-plus-fix push) is accepted with no diff read.

## The limits

- Kind, Guard or check, and docs-only are the lane's own claims. The tool does not check paths. It does not tell a record that files an owner ruling from other docs. Kind stays the lane's claim. Guards stop mistakes, not attackers (record `guard-guards-mistakes-only`).
- Open: an integration PR has no record of its own.
- A `delete-only` change with Guard or check `no` and a round 1 FAIL reads done (rule `roles-review-cap-three`, the three-round review cap). The lane fixes the defect and posts a new review record for the new head, before the batch runner batches it. The fix push makes the old record stale.
- Unmeasured: whether the auto-mode classifier allows `merge --reviewed` and `merge <pr> --review-record`. Both are off `merge/cloud_allow.json`, which allows only `--confirm` and `--role`.
- One fix check per record. A second fix on a fixed head starts a new lane at round 1. `--fix-check` refuses unless its reviewed head equals the Head of the newest earlier record on the PR and that record has no Fix check line. Owner page item 418 (fix-checks-chain) is where a second fix check is decided.
- The tool cannot see whether a Findings count is true, or whether a debt edit is that finding's own. It cannot see a follow-up PR's topic, or whether a finding got its own roadmap step. Pre-cut-off records with no Findings line keep today's verdict.
- The tool does not see whether a fix-check push is filing-only. The fix-check reviewer reads the diff.

## Lane picks

The coordinator answered both at 23:14. Process-only.

- Q1. Should preview or confirm refuse a PR with no valid record? Pick a: no refusal now. Ruling 113 a names discovery only (rule `outcomes-grant-covers-named-act`). Not taken: confirm refuses an integration PR when a lane tip has no done record. Also not taken: preview prints a review line only.
- Q2. Which wins when a decision record and rule `roles-review-cap-three` disagree? Pick a: the rule outranks a decision record. Round 3 counts as done, whatever its verdict. Not taken: a final PASS is always needed. Record `standing-merge-grant` says so now.

Kind: process
Home: merge/merge.py
