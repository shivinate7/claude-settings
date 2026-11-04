# Docs-only pull requests skip the reviewer

## The ruling

Owner, 2026-09-26: a pull request that changes only prose or docs, and touches no rule, guard, check or product code, gets no reviewer pass, except a ruling record (owner, 2026-11-04 07:56 CST, waiting-page item 205 b, "ruling records get a short review"). Report its PR and its CI verdict. A change that can move a verdict still gets a reviewer.

Why: a review of a change that simple is wasted. `roles-solo-reviews-logic-diffs-only` says the same for solo mode. This record extends it to every other session shape.

A ruling record is a decision record, or any repo record that carries an owner ruling. A pull request that files or rewrites one is not docs-only for review. It gets one short reviewer read before it merges. The reader checks two things: whether the record matches the ruling's words, and whether it contradicts an older ruling on the same question.

The review record is `Kind: normal`, `Guard or check: no`, and one `Round` line. It is never `docs-only`. The read is one round, and its report runs about 10 lines.

Not taken: "skip the reviewer, flag a clash"; "as today" (no read for ruling records).

## The cost

One reviewer read per ruling record. No new process, file or timer. The reader runs the reviewer's round-1 model, haiku today (the reviewer row of decision `agent-model-cap`, the model-per-role table).

Kind: process
Home: rule:roles-solo-reviews-logic-diffs-only
