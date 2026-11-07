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
- The `Fix check` line is optional, comes once after the Round lines, and is not a round (record `hold-unsafe-after-round-3`). `--fix-check HEAD:reviewer:MODEL:VERDICT` writes it. Its reviewed head must differ from Head. A FAIL is open. A PASS counts as its round passing in any round; after round 3 it keeps the net value round 3 gave; with no round recorded it reads open.
- The comment never stores CI state. The merge tool reads CI live. `merge --reviewed` shows a draft
  PR as `CI draft, no run`, because a draft has no CI run.
- A body is not a record when the marker is missing, a field is malformed, round numbers skip, or a round is above 3.
- The newest record for a head counts. A record for an old head is stale.
- `merge <pr> --review-record --head <40-hex sha>` prints the body for the head the review read. When the PR's live head is another sha, it stops with exit 1 and prints no body, so a record never names a head the review did not read. A later push can still reuse the rounds, as a new record for the new head with the same Round lines. The carried-run check in the limits covers that, and refuses when an earlier record of this PR cannot be read.
- A lane posts the body with the GitHub MCP comment tool after each round. `gh pr comment` uses GraphQL, which the cloud refuses (route graphql-gh-api-cloud).
- The one home of the form is the merge tool (`merge/merge.py`). `review_body` writes the body, `parse_review` reads it, and `review_state` gives each record's state. `reviewed_lines` prints the `--reviewed` list, `earlier_records`, `carried_first_head` and `unreviewed_guard_paths` make the carried-run check, `round_arg` reads `--round`, and `Host.review_comments` makes the one list read.

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

## The cost

Counted as real `gh` calls, one call per list read however many pages it pages.

- `merge --reviewed` makes two list calls per run. One lists the open PRs. The other lists the repo's issue comments since the oldest open PR, so it pages every comment of the repo since then, not only review records. The cost grows with the repo's comment traffic and with the age of the oldest open PR.
- Not a `gh` call: each `--reviewed` run also runs one `git fetch origin main` (`load_config`) and local git reads.
- Each ready PR that has a record adds three calls: the check runs, the commit statuses and the branch protection (required checks mode `protection`). A draft, and a PR with no record, add none.
- One ready PR with a record: five calls. With a pinned `merge.requiredChecks` list: also five, because the one protection compare moves to the start of the run and the per-PR protection read goes.
- `merge <pr> --review-record`: three `gh` reads per call, the PR, one paged list of its changed files and one paged list of the repo's issue comments since the PR opened. `--fix-check` reuses that comment read. The test `ReviewGuardCost` pins them. When the new record carries the rounds of an earlier one, the call also runs one `git fetch origin` (the base, the first head and the new head) and local git reads, and no more `gh` calls. It writes nothing.
- The carried-run check adds one `git fetch origin` to `merge --reviewed` for each PR whose done record carries rounds, and no `gh` call. A PR with one record, or a record whose rounds are new, adds none.
- No new long-lived process, file, cache or timer. The batch runner calls the list at each wake. A lane calls the render at each round.
- The test `ReviewedList` in `merge/test_merge.py` pins the two list reads and the five calls for one ready PR.

## The limits

- `--review-record` reads the PR's changed files. A moved file counts at its old path too.
  - It refuses Guard or check `no` when a path starts with an entry of `GUARD_PATHS` or equals one of `GUARD_FILES`. `GUARD_PATHS` is `stale_cites.RULE_DIRS` plus `merge/` and `githooks/`. `GUARD_FILES` is `settings.json`. A test path (`hooks/guard.py` `is_test_rel`) never counts, because test files alone never count (record `hold-unsafe-after-round-3`).
  - It refuses a files list shorter than the PR's changed-file count, and a PR read that gives no count. GitHub lists at most 3000 files.
  - `agents/*.md` is not on the list. Only its `tools` lines are a guard, and a path cannot tell those apart from prompt text.
  - It refuses Kind `docs-only` when a path does not end in `.md`. It refuses Kind `delete-only` when a path is not removed.
  - Guard or check `yes` stays allowed with no hit, because a guard can live outside those paths.
- The files path check above (Guard or check `no`, Kind) runs only when `--review-record` writes a record. `merge --reviewed` does not read the PR's files. A record posted by hand is trusted for those two fields.
- A review record carries the rounds of an earlier record when its Round lines and Fix check equal the newest earlier record's. A run of such records is unbroken. R is the newest record. H1 is the Head of the oldest record in R's unbroken run, and H2 is R's Head (for `--review-record`, the head it writes). `merge-tree --write-tree` merges H1 with the merge base of H2 and `origin/<base>`, giving tree A. Then main's own commits and a clean merge of main cancel out, and what is left between A and H2 is the lane's own work and any conflict resolved by hand.
  - When a guard or check path (the list above) changed between A and H2, no reviewer read it. `--review-record` refuses with exit 1 and prints no body. `merge --reviewed` shows the PR `open`, and its reason names H1 and each path.
  - Let through: a Fix check whose reviewed head is H1 (its Fix check line differs from the earlier one, so nothing is carried), and a new Round line (it breaks the run, so the run starts at that record).
  - Fail closed: when H1 cannot be fetched, `merge-tree` fails, or git is older than 2.38, `--review-record` refuses and `--reviewed` shows `open`.
  - A first record with no earlier record skips the check.
  - Who is a predecessor (`earlier_records`, one helper for `--review-record` and `--reviewed`): a record that names another PR is a stray paste and is skipped, never a predecessor. A record of this PR that does not parse fails closed: `--review-record` refuses naming the PR and that its record could not be read, and `--reviewed` shows `open` with the same reason. It is never skipped to an older record.
  - Limit: a first record posted for a head nobody reviewed is unseen. No earlier record names an earlier head, so nothing is carried. A lane that posts a record for a head it did not review is a mistake the tool cannot see.
- In another repo, a change under `hooks/`, `lint/`, `bin/`, `actions/`, `.github/`, `merge/` or `githooks/`, or to a root `settings.json`, must say Guard or check `yes`. It then owes the net-value test after round 3. A `.claude/settings.json` or `.claude/hooks/` path is not on the list.
- The tool does not tell a record that files an owner ruling from other docs. Kind `normal` stays the lane's claim. Guards stop mistakes, not attackers (record `guard-guards-mistakes-only`).
- Open: an integration PR has no record of its own.
- A `delete-only` change with Guard or check `no` and a round 1 FAIL reads done (rule `roles-review-cap-three`, the three-round review cap). The lane fixes the defect and posts a new review record for the new head, before the batch runner batches it. The fix push makes the old record stale.
- Unmeasured: whether the auto-mode classifier allows `merge --reviewed` and `merge <pr> --review-record`. Both are off `merge/cloud_allow.json`, which allows only `--confirm` and `--role`.
- One fix check per record. A second fix on a fixed head starts a new lane at round 1. `--fix-check` refuses unless its reviewed head equals the Head of the newest earlier record on the PR and that record has no Fix check line.

## Lane picks

The coordinator answered both at 23:14. Process-only.

- Q1. Should preview or confirm refuse a PR with no valid record? Pick a: no refusal now. Ruling 113 a names discovery only (rule `outcomes-grant-covers-named-act`). Not taken: confirm refuses an integration PR when a lane tip has no done record. Also not taken: preview prints a review line only.
- Q2. Which wins when a decision record and rule `roles-review-cap-three` disagree? Pick a: the rule outranks a decision record. Round 3 counts as done, whatever its verdict. Not taken: a final PASS is always needed. Record `standing-merge-grant` says so now.

Kind: process
Home: merge/merge.py
