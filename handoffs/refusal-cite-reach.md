# Handoff: lane refusal-cite-reach

Written 2026-11-02 12:55 CST, at the owner's wind-down (owner instruction 12:31 CST, relayed by the coordinator).

## Goal

Roadmap step refusal-cite-reach: every refusal cites its rule. It widens the uncited-refusal check (`lint/test_rule_audit.py`, `refusal_problems` and `REFUSAL_UNCITED_EXEMPT`) beyond guard*.py, to:

- the guard-crash refusal in hooks/guard.py
- the judge hooks: blind_brief, call_judge, prose_judge and sendmessage_state
- every merge/merge.py stop: raised, returned, or built by a helper

It also turns the 13 exempt ids that can cite now into cites. The 7 later ids stay exempt, each with its reason.

## Rulings that govern it

- speak-cite-id-plus-gloss: every id carries a short gloss.
- git-cite-by-id: cite ids, not paths.
- git-remedy-never-names-target: a remedy never names the forbidden target.
- building-allow-list-is-the-constant: exempt keys point at emitted ids or code, never at a copy.
- building-one-home-per-capability: extend the one check, never build a second.
- Lane ruling, 2026-11-01 22:44 CST: item-field-rendered and page-stale have records, so they cite now and leave the exempt list.

## State

- Branch: `lane/refusal-cite-reach`, head fc78547f. That head is 0e8edd82 plus a clean merge of main 74be1279. It holds no other change.
- PR #1061 (this lane): draft, base main. Review: 3 rounds. Round 3 PASS, net safety value zero, 2026-11-02 02:29 CST.
- Batch: batch 69 holds #1061 at 0e8edd82. Its first integration PR, #1102, was closed unmerged. The batch runner moved batch 69 to a fresh draft PR from branch `batch-69` (head 1fcb71a2). Its number is not recorded here; batch runner 7 owns it.
- Local checks at fc78547f, all PASS:
  - test_rule_audit
  - merge/test_merge.py and merge/test_lane_lint.py: 847 passed
  - hooks/test_guard.py: 5545 of 5545
  - test_sendmessage_state, test_blind_brief, test_call_judge, test_prose_judge, test_question_form
  - check_silent_undo --strict
  - `ci-job checks --lint`: 0 FAIL
  - hook_catalog --check: nothing stale

## Done

- The check reads printed refusals, the judge hooks, merge.py `raise` and `return` of Stop and its subclasses, the helpers fail(), keep(), prove and stamp_stop() (including `kind=`), `"\n".join([...])`, and lambdas. Each exempt merge site is keyed by function plus message prefix.
- The 13 ids cite their decision records. The 7 later ids stay exempt with reasons.
- Six follow-up notes are in docs/debts/notes.md: cite-reader-* and merge-*.

## Next step

1. When batch 69's integration PR merges, close #1061 as replaced by it.
2. If batch 69 drops #1061: fix in the lane, merge main, run the suites above, and send the new head to the batch runner.

## Open items and owners

- Candidate step, sent to triage 5: Stop-hook `decision: "block"` prints in ruling_home.py, precompact_handoff.py and report_guard.py are not read by the check. Owner: triage.
- Guard gap: builder-test-edit missed a `python3 - <<EOF open(p,'w')` write and a `git show ... > test file` redirect. Owner: lane builder-test-edit-heredoc.
- Exempt list: the key `merge:lane_lint: moved: gh says` was added after main 62bdb8a6. It covers an already-exempt stop that is now also reached from lane_lint. The list header says the list only shrinks. That is a wording gap, with no owner yet.
- No owner questions are open.

## Unpushed work

None. Every subagent's commit is on origin `lane/refusal-cite-reach`.
