# Handoff: lane tier-boundaries-enforced

Wound down on the owner's order (via coordinator, 2026-11-02 12:31 CST).

## Goal

Owner, 2026-10-31 15:31 CDT: enforce tier boundaries by mechanism, "like an actual fix". Sessions
"kindly point me in the right direction".

## Owner rulings

- 111 a (2026-11-01 11:53 CST): in a coordinator build, the batch runner runs every merge. The
  coordinator runs no build or review agents. Solo and one-lane sessions keep merging. Home: decision
  session-tiers, "Tier guards" (PR #919 and PR #1042).
- 112 a (2026-11-01 16:45 CST): the coordinator-scope guard refuses. A typed override lifts one act.
  Each refusal or override writes one guard.log line. Home: session-tiers (PR #919).
- 113 a (2026-11-01 04:26 CST): each PR carries a review record. The batch runner finds reviewed,
  green PRs itself. No merge message. Home: decision pr-review-record (PR #1065).
- Process-only Q1 a and Q2 a (coordinator, 2026-11-01 23:14 CST): preview and confirm add no
  refusal. Rule roles-review-cap-three outranks the sentence in standing-merge-grant. Home:
  pr-review-record (PR #1065).
- Owner, 2026-11-01 23:31 CST: each owner question goes to the coordinator by send_message in the
  turn it is asked.
- Coordinator, 2026-11-02 10:20 CST: no new Bash allow for a reviewer's read-only probe. A reviewer
  reads the code instead. Recorded as note classifier-refused-read-probe in PR #1065.
- Lane, 2026-11-02 10:50 CST: a session with no transcript or no own record is not a coordinator.
  The guard fails open, since guards stop mistakes. Home: session-tiers (PR #919).

## PRs (all drafts; never mark ready, never merge; the batch runner merges)

### #1065: review record on each PR (branch review-record)

- Head 42fdc26739579563973114885794127cb282cf36, with main 74be1279 merged in cleanly.
- Round 1 reviewer (haiku): FAIL. Main's `merge --lane-lint` steer was lost. The fix restored it.
- Round 2 reviewer (sonnet): PASS on 1df70a69. Net value: not owed.
- Checks on 42fdc267: test_merge, test_guard, check_silent_undo --strict and ste-changed all pass.
  hook_catalog reports only docs/records.md as stale, which is allowed.
- No review record is posted for 42fdc267. The newest record (comment 6583248037) names 1df70a69.
- Batch runner 7 (12:02 CST): #1065 conflicts with #1061 in merge/merge.py, so it goes to batch 70.
- Next:
  1. After batch 69 merges, merge the new main and resolve merge/merge.py (builder sonnet).
  2. Run the checks above.
  3. Post a review record for the new full 40-character head. Use rounds 1 haiku FAIL and
     2 sonnet PASS, plus a review of the merge resolution if merge.py logic changed.
  4. Send the head to the batch runner.

### #919: the coordinator-scope guard (branch tier-boundaries-enforced)

- Head 568e606e03039ad0672031c71d631d4a87118bf4: a WIP commit from the round-3 builder (opus),
  stopped by the wind-down.
- Defect found 2026-11-02: main 62bdb8a6 lets only the batch runner write a merge role. So #919's
  old test, "role file says coordinator", could never fire.
- The fix: own_tier_tagged in hooks/guard_merge.py. The guard reads the session's own tags from its
  newest own get_session record, plus own set_session_tags adds, minus own removes. It reads the
  transcript only for a write that would be refused. merge.py and shared_names.py now equal main.
- Review rounds:
  - Earlier round 1 passed.
  - Fix round 2 (sonnet): FAIL. The blocker was a test gap: the cost rows allowed one transcript
    open. Fixed in 75dfddf7 (test-author).
  - Round 3 builder (opus, "Round 3 of 3"): its tasks were case (h), own record then own remove
    passes; session-tiers.md near line 81, the detection text; the cost line near line 83, which
    every cloud session pays (22-36 ms for a shell write that names a repo path, about 50 ms for the
    transcript read on a refusal only); and notes.md near line 829.
- Round 3 state at 568e606e:
  - Item 1 is built: hooks/guard_merge.py _own_session_read and own_tier_tagged (about lines 521-575)
    and a guard.py comment (about lines 3982-3985). The third value of _own_session_read now holds
    the session's current own tags. Element [0] stays the raw record tags, so the merge-role-proof
    rule is not loosened.
  - No check has run on 568e606e.
  - Not done: item 2 (session-tiers.md line 81 and the Limits line near 84), item 3 (the cost line
    near 83) and item 4 (the last sentence of docs/debts/notes.md line 829).
  - Item 5 was dropped on purpose. If a tag call counted only once its result arrives, a write sent
    in the same message would pass.
- Next:
  1. A builder finishes items 2-4 and runs all checks (test_guard, test_shared_names,
     test_session_start, test_merge, check_silent_undo --strict, hook_catalog --check with only
     records.md stale, and ste-changed). This is still round 3 of 3.
  2. Round 3 reviewer (sonnet, "Round 3 of 3") with the net-value test (rule roles-review-cap-three).
  3. Post a review record for the head.
  4. Send the head to the batch runner.
- Drops-lines trailers:
  - hooks/guard_frozen.py drops only #919's own sed-operand feature (round 2 checked it).
  - The merge.py trailer in 01bb1125 is now moot.

### #1042: the coordinator-acts guard (branch coordinator-acts)

- Head 49adc89e5fcf52dd7271b5a4c6f61011b66c4856, unchanged. It contains the old #919.
- Its merge of #919 stopped on conflicts. Not started again.
- Next, after #919's fix passes review:
  1. Merge the new #919 head, then main.
  2. Conflicts in docs/decisions/session-tiers.md (3 hunks) and hooks/session_start.sh (lines
     18-22) go to a builder.
  3. The conflict in hooks/test_session_start.py (lines 43-61) goes to a test-author. Resolve it as
     a union: keep normal_tier_line, keep sentences, and keep merge_role_sentence with its anchor
     parameter.
  4. Check whether coordinator_act_hit's helper _cloud_coordinator gates on the role file. If it
     does, point it at own_tier_tagged.
  5. A review round, then post a review record.

## Unstarted lanes

- Debt session-start-handoff-text: hooks/session_start.sh line 18 still says to hand merges to the
  batch runner. Waits for #1042.
- Debt mcp-merge-matcher-missing: merges through the GitHub MCP tools never reach the guard. Waits
  for #1065.

## Not pushed

- Worktree .claude/worktrees/agent-aa323becbdfa5fa3a holds 67 staged files on ede26fc9 (05:57 UTC).
  ede26fc9 is already in review-record. This is a stale, superseded merge attempt with nothing to
  save.

## Open questions

- None for the owner.
