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
Net value: not owed|zero|positive|negative
CI: read live by merge --reviewed
```

- The first line is the marker.
- One `Round` line per reviewer. A round can hold more than one line.
- The comment never stores CI state. The merge tool reads CI live.
- A body is not a record when the marker is missing, a field is malformed, round numbers skip, or a round is above 3.
- The newest record for a head counts. A record for an old head is stale.
- A lane posts the body with the GitHub MCP comment tool after each round. `gh pr comment` uses GraphQL, which the cloud refuses.
- The one home of the form is the merge tool (`merge/merge.py`). `review_body` writes the body, `parse_review` reads it, and `review_state` gives each record's state. `reviewed_lines` prints the `--reviewed` list, `round_arg` reads `--round`, and `Host.review_comments` makes the one list read.

## The done rules

A change is done when one of these holds (rule `roles-review-cap-three`):

- its last round is PASS;
- round 3 is done, and Guard or check is `no`;
- round 3 is done, Guard or check is `yes`, and Net value is zero or positive;
- Kind is `delete-only`, and round 1 is done;
- Kind is `docs-only`, with zero rounds (record `docs-only-prs-skip-review`).

A round 3 verdict does not decide done. Net value does, when Guard or check is `yes`: `negative` holds the change (record `hold-unsafe-after-round-3`).

## The cost

- `merge --reviewed`: two list reads per call. One lists the open PRs. The other lists the repo's issue comments since the oldest open PR. It adds one check read for each ready PR on the list.
- `merge <pr> --review-record`: one PR read per call. It writes nothing.
- No new process, file or timer. The batch runner calls the list at each wake. A lane calls the render at each round.
- The test `ReviewedList` in `merge/test_merge.py` pins the two list reads.

## The limits

- Kind, Guard or check, and docs-only are the lane's own claims. The tool does not check paths. Guards stop mistakes, not attackers (record `guard-guards-mistakes-only`).
- Open: an integration PR has no record of its own.
- Unmeasured: whether the auto-mode classifier allows `merge <pr> --review-record`.

## Lane picks

The coordinator answered both at 23:14. Process-only.

- Q1. Should preview or confirm refuse a PR with no valid record? Pick a: no refusal now. Ruling 113 a names discovery only (rule `outcomes-grant-covers-named-act`). Not taken: confirm refuses an integration PR when a lane tip has no done record. Also not taken: preview prints a review line only.
- Q2. Which wins when a decision record and rule `roles-review-cap-three` disagree? Pick a: the rule outranks a decision record. Round 3 counts as done, whatever its verdict. Not taken: a final PASS is always needed. Record `standing-merge-grant` says so now.

Kind: process
Home: merge/merge.py
