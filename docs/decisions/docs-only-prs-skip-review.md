# Docs-only pull requests skip the full review

## The ruling

A pull request that changes only prose or docs, and touches no rule, guard, check or product code, gets no full review. Report its PR and its CI verdict. A record in it that files an owner ruling gets the short round below. A change that can move a verdict gets a full review.

Sources: owner, 2026-09-26 (no reviewer for a docs-only PR); owner, 2026-11-04 07:56 CST (waiting-page item 205 b, a short read for a record that files an owner ruling). The second ruling's source is the coordinator's brief. The waiting page is not in this repo.
Express pass: owner, 2026-11-10 14:12 CST, relayed by the retrospective session: `if we develop some sorta express pass for the entirety of prose to be fast to review i'd be open to considering that`; 15:22 CST: `this is very key yes` (restart plan R7, section 3.13). The words "match the feedback log word for word" are the plan's, not the owner's.

Why: a full review of a change that simple is wasted. A record that files an owner ruling can still misquote the ruling. `roles-solo-reviews-logic-diffs-only` says the same for a run with one lane. This record extends it to every other session role.

## The round

When the brief says the change files an owner ruling, round 1 checks two things only. It checks that the record matches the ruling's words, and that it contradicts no older ruling on the same question. The report stays under about 10 lines (the coordinator's brief for waiting-page item 205 b).

The review record is `Kind: normal`, `Guard or check: no`, with one `Round` line. It is never `docs-only`.

A FAIL follows rule `roles-review-cap-three` (the three-round cap). A PR that also changes a rule, guard, check or code gets a full review, not this two-check round.

Express pass: a record whose every owner quote matches the owner's words in the feedback log, word for word, skips this round. The match replaces the first check, which catches a paraphrase, a widened act and a wrong time. One quote that differs, or has no log entry, keeps the round. The review log is still posted. First user: the restart plan's follow-up plan PR. Departs from: main — the round runs for every such record; with a full quote match it does not. Reader (owner, 2026-11-12 14:13 CST, page item 624 b, "for now at least"): the sending session checks the quotes against its own feedback file and writes a stamp line in the review log. The merge tool trusts the stamp, as it trusts `--reviewed`. A later move to a shared log stays open. The feedback file is a per-session file outside git (decision `owner-feedback-inbox`), so the merge tool cannot read it. The stamp is the session's word, not a read of the log. The merge tool change is built in step express-pass-owner-quotes, part 2. Until it lands, the round is the only path and the express pass skips nothing.

Not taken: "skip the reviewer, flag a clash"; "as today" (no round for a record that files an owner ruling); a quote match against a file the PR's own author wrote.

## The cost

One reviewer run per record that files an owner ruling, less each one the express pass skips. The express pass adds one read of the log per such PR, in a process already running; no new process, file or timer. Round 1 runs the reviewer's round-1 model, haiku today (the reviewer row of decision `agent-model-cap`, the model-per-role table).

Kind: process
Home: rule:roles-solo-reviews-logic-diffs-only
