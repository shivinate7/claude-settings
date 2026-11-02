# Handoff: lane red-main-same-sha-green

## Goal

The red-main check (merge/merge.py `Host.base_state`, decision no-merge-onto-red-main, no batch merges onto a red main) refuses banchi #1003. Main's red schedule run 41436198024 is not cleared by the newer green dispatch run 41483723188 on the same sha (471dc268). The fix: a newer completed run on the same or a newer main sha clears the red when its jobs cover and pass the red run's not-passed jobs. The CI alarm (actions/ci-alarm/alarm.sh) gets the same rule.

## Measured cause

- The red jobs are `design-check (4)` and `all-jobs-passed`. Both are `success` in the green run.
- The clear is blocked by `nightly-alarm`, which is success in R and skipped in N, and by `ci-done`, which is skipped in both runs. `design-check-passed` is not the cause: it is success in N.
- The coordinator adds: `nightly-alarm` runs only when a needed job failed or was cancelled (check.yml `if:`). So it is skipped in every green run, and the old rule "every job of R passes in N" can never clear such a red.

## Owner rulings and open questions

- Owner item 166 (stale decision: change the sentence "Every job name in R appears in N ... `success`" in no-merge-onto-red-main) is OPEN. The coordinator owns it. The coordinator recommended "change nothing" there. The lane recommended option 1: cover every job of R that did not end success or skipped, plus a sha check. Do not merge before the owner rules.
- Wind-down: owner instruction 12:31 CST, 2026-11-02.

## State

- Branch `red-main-same-sha-green` on origin, head 64cf676e (WIP). It holds:
  - 2532264d: test-author red cases (merge/test_merge.py class RedMainBrake, actions/ci-alarm/test_action.sh). Cases: the banchi runs, a newer run on an older sha, a failed compare read, a newer sha, a missing head_sha on either side, schedule-only failed, a cancelled job that N lacks, and the re-pointed lacks-a-passed-job case.
  - eea96a80: builder fix. Shared helpers `cover(r, cancelled)` and `cleared(r, cancelled=False)` in base_state, and `holds_head` for the sha check. The alarm.sh twin.
  - 8f85d034 and 64cf676e: merges of main 74be1279 (batch 68, with #1092 merge-stale-cancel). #1092's cancelled-run clear is kept.
- Verdicts on 64cf676e: `check_silent_undo --strict` PASS. `bash actions/ci-alarm/test_action.sh` PASS. pytest merge/test_merge.py was NOT run on this head; it passed on a scratch copy before the final commit (835 passed, 6 skipped). `ci-job checks --lint` was NOT run on this head.
- No PR is open. No review round has run. The decision record is not yet rewritten.
- Local branches not pushed are folded into the pushed head: red-main-same-sha-green-build (64cf676e) and the test-author's red-main-same-sha-green (8f85d034).

## Next

1. On 64cf676e, run through verdict: `python3 -m pytest merge/test_merge.py -q`, `~/.claude/bin/ci-job checks --lint`, `~/.claude/bin/merge --lane-lint <pr>`.
2. After the owner rules on item 166: if option 1, rewrite the cross-group bullet of docs/decisions/no-merge-onto-red-main.md in place. Add a Risk line (banchi #1003, runs 41436198024 and 41483723188, 2026-11-02) and add the compare read to its Cost line. If "change nothing", archive the branch and close the lane.
3. Open a draft PR. A fresh reviewer (sonnet) runs the net-value test (hold-unsafe-after-round-3): name every red that must still refuse.
4. Send the PR number, head and review verdict to batch runner 7 (session_013NEJKyjt96cx7d1uCdtb8U) and to the coordinator.
