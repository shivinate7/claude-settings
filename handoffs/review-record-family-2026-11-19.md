# Handoff: lane review-record-family (2026-11-19)

Session: session_013NEJKyj7W9KzfTxBFwwmuL (started 2026-11-13 11:33 CST under owner grant R67, drain-first). Repo: shivinate7/claude-settings.

## Task

Rebuild the review-record family in order: #2326 (review-record stack), then steps review-record-past-head (#2365) and review-record-provenance (#2440). Fresh branches from main; old PRs are input, never a base.

## State

| PR | Branch | Head | State |
|---|---|---|---|
| #3185 (past-head core, replaces #2365, #2200, #2277, #1951) | review-record-past-head-core | 40edc5ef6 | open, draft. Held by the Coordinator (13:39 CST Nov 13) until lane merge-tool-r9-no-round-3 (session_013NEJL3Q9buRa5se7edKbyN, owner 741 a) lands. |
| #2326 | review-record-stack (old branch, not mine) | 9efd6bbc4 | open, draft. Not rebuilt. |
| #2440 | record-guard-wrapper-forms (old branch, not mine) | c028c1926 | open, draft. Not started. |
| #2365, #2200, #2277, #1951 | old branches kept | | closed 13:16 CST Nov 13 by runner 10 (owner ruling close-replaced-at-open); reopen if #3185 is dropped. |

States read from the GitHub REST API at 00:3x CST Nov 19.

## Done

- Step 0: homes found and sent to triage and the Coordinator. Item 347 a is on step review-fix-check-round. Items 356 a, 362 b and 363 b are page items (triage: round3-fail-holds, round3-partial-holds, round3-fixcheck-clears). WIDE has no home anywhere. The round floor commit e0521195b is not carried by the rebuild.
- #3185 built (test-author haiku, builder sonnet): a record whose last round is all FAIL, no fix check, may name an ancestor of the live head when it is one of the PR's own commits. Tests: class ReviewLogPastHead, 10 cases, mutants shown red.
- Reviews (reviewer sonnet each): round 1 PASS at 483d55bae; fix check PASS (lint fixes); round 2 FAIL at 5102495fe (two unpinned clauses); fix check PASS and round 3 PASS, net value zero, at f9076beba; fix check PASS over 5102495fe..40edc5ef6.
- Records posted on #3185: round 1 (483d55bae), round 1 + fix check (5102495fe), rounds 1+2 (5102495fe), rounds 1-3 + fix check (f9076beba). No record at 40edc5ef6.

## Unfinished

- #3185 has no valid review record at 40edc5ef6. `merge --review-record --head 40edc5ef6 ... --fix-check 5102495fe:reviewer:sonnet:PASS` is refused: the fix check must start from the Head of the newest earlier log, and that log must have no Fix check line. The lint-only comment commit 40edc5ef6 is what made the second fix. Lane lint failed at f9076beba (comment narration) and has not been re-run at 40edc5ef6.
- The lane-touched-tests Windows and macOS matrix job was skipped at 483d55bae, 5102495fe and f9076beba. Unknown, not green. Triage found no ruling on whether a skip is acceptable.
- #2326 and #2440 not started. #2326 waits on rulings (WIDE no home; 356 a conflicts with main's line on a round-3 FAIL and with R9). #2326 and #3185 both carry the #1828 slice (a FAIL record naming an ancestor head).

## Next step

When merge-tool-r9-no-round-3 lands: post the fix check at 40edc5ef6 with the tool, re-run `merge --lane-lint 3185`, read the lane-touched-tests run, hand in to the batch runner (session_013NEJL2f1YCYsvLdpFqtWP3). Then #2440 (core: REVIEW_STAMP_SALT, cutover read, edit-route and GraphQL review-record guard, comment-post guard; maybe carry #1751's two commits; ledger row in docs/backlog-drain/verdicts.tsv on #3154).

## Notes filed with triage (step review-record-past-head, roadmap 37f853d02)

Grant not passed at merge/merge.py:5539; stderr "stale" wording at :5789; README line 173 omits "no Fix check line"; merge.py docstring lines 24-25; a past-head log can shadow a done live-head log; "record" wording against the glossary's "review log"; the "coordinator, 2026-11-08 11:43 CST" cite in pr-review-record.md has no other home.

## Refused acts

- `merge --review-record` with a second fix check at 40edc5ef6 (above). I did not hand-write a record. The Coordinator ruled: no ruling read around the tool, no revert, hold at 40edc5ef6.
- Push to the old branch review-record-past-head (the old #2200 branch): refused by git as non-fast-forward; I used review-record-past-head-core.

## Owner rulings held

- R9 (roadmap/rulings/r9.json): a guard or check change that passes round 1 is done; round 3 only for one fixed under a fix verifier. The Coordinator read it two ways on #3185, last at 13:39 CST Nov 13: round 3 owed.
- Close-replaced-at-open (owner, 13:12 CST Nov 13, Option A): a replaced PR closes when its replacer opens.
- Grant R67 drain-first (owner, 10:50 CST Nov 13): the task's grant. Home roadmap/rulings/drain-first-hold.json on origin/roadmap; not on main.

## Agents (all finished; worktrees under /home/user/claude-settings/.claude/worktrees/)

- test-author haiku, red tests: agent-a9b917479b3fbeafa (b54090d79)
- builder sonnet, past-head path: agent-aca565ee3bc5b03de (483d55bae)
- reviewer sonnet round 1: agent-a57dbdb5ee338d379
- builder sonnet, doc fix: agent-a52a655690ae0f3eb (9089e9bd5); test-author haiku rename: agent-aa6b1c32a1b8f5c60 (82d7cfb28); pushed together as 5102495fe
- reviewer sonnet fix check: agent-a221c1497bd7e529a
- reviewer sonnet round 3 (stopped, replaced): agent-a756bb17dda3d7bc3; round 3 kept: agent-a7a2477b710c16935 (f9076beba); also agent-aaa8bb6dbed31e687 (round 3 at 5102495fe), agent-ab315b1ee508a589f (round 2), agent-a50b12c25fc963f65 (fix check)
- test-author haiku, mutant cases: agent-a3612d1b293cc5aa3 (f9076beba); comment reword: agent-a7c88b5d9420b709c (40edc5ef6); reviewer sonnet fix check: agent-a2ddc752a57c01215
