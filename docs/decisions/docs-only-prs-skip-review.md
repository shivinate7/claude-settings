# Docs-only pull requests skip the full review

## The ruling

A pull request that changes only prose or docs, and touches no rule, guard, check or product code, gets no full review. Report its PR and its CI verdict. A record in it that files an owner ruling gets the short round below. A change that can move a verdict gets a full review.

Sources: owner, 2026-09-26 (no reviewer for a docs-only PR); owner, 2026-11-04 07:56 CST (waiting-page item 205 b, a short read for a record that files an owner ruling). The second ruling's source is the coordinator's brief. The waiting page is not in this repo.

Why: a full review of a change that simple is wasted. A record that files an owner ruling can still misquote the ruling. `roles-solo-reviews-logic-diffs-only` says the same for solo mode. This record extends it to every other session shape.

## The round

When the brief says the change files an owner ruling, round 1 checks two things only. It checks that the record matches the ruling's words, and that it contradicts no older ruling on the same question. The report stays under about 10 lines (the coordinator's brief for waiting-page item 205 b). For a decision record removed or renamed out, round 1 checks instead that the PR names the ruling that withdraws it and that no record still cites its slug (lane pick, process-only; coordinator ruling 2026-11-07 15:17 CST, which makes a removal a change that takes this round).

The review record is `Kind: normal`, `Guard or check: no`, with one `Round` line. It is never `docs-only`, and a removal is never `delete-only`.

A FAIL follows rule `roles-review-cap-three` (the three-round cap). A PR that also changes a rule, guard, check or code gets a full review, not this two-check round.

Not taken: "skip the reviewer, flag a clash"; "as today" (no round for a record that files an owner ruling).

## The cost

One reviewer run per record that files an owner ruling. No new process, file or timer. Round 1 runs the reviewer's round-1 model, haiku today (the reviewer row of decision `agent-model-cap`, the model-per-role table).

Kind: process
Home: rule:roles-solo-reviews-logic-diffs-only
