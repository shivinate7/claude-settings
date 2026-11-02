# Handoff: trial-lg (lane tracking-turn-report-clash)

## Goal

Settle the clash between two rules. Rule `output-tracking-turn-one-line` (one line on a
turn that only tracks running work) and the report guard (`lint/report_guard.py`, the full
report on a turn that commits, pushes or merges). Roadmap step
`tracking-turn-report-clash`, frozen at roadmap f122aabe.

This was a trial run. The base is commit 4b8037d4, not main. The only push target is
`archive/trial-lg`. No PR was opened.

## Owner rulings

- 2026-11-01 16:23 CST (question box, cited in the step): "every turn that pushes ends with
  the report" is how things already work, not a change.
- 2026-11-02 12:31 CST (relayed by the coordinator): wind down. Start no new work.

## Branch and state

- Branch `archive/trial-lg` on origin. The lane commits sit under this handoff commit:
  - 519083ec: the style sentence in `output-styles/shiv-stylisms.md` (record-writer haiku)
  - e11d5ee8: the rule's row in `lint/rule_mechanisms.json` becomes `check`, citing
    `test_67_every_github_landing_tool_with_no_report_blocks`. `JUDGMENT_EXPECTED` in
    `lint/rule_audit.py` moves from 25 to 24 (builder sonnet)
  - b15c2b8b: the row's reason names the guard's real landing set (orchestrator)
- Review: round 1 PASS (reviewer haiku). Rounds 2 and 3 did not run.
- Checks at b15c2b8b: ste-changed against 4b8037d4 PASS. rule_audit PASS.
- PRs: none. This was a trial, so there is no draft PR and no hand-off to the batch runner.
- Nothing is left unpushed. The builder's branch `tracking-turn-report-clash-json`
  (13da4b83) was cherry-picked into the lane as e11d5ee8.

## Done

The style sentence and the mechanism row match the step's done check, on the trial base.

## Next step

For a real run, rebase the three commits onto main and open a draft PR. Main 49a41651
already holds a version of the sentence, so first check whether the lane is still needed.

## Open questions

- Owner: the guard misses `gh pr merge`, `gh pr create`, `git revert`, `git cherry-pick`,
  `delete_file` and `update_pull_request_branch`, but the sentence promises a report on
  those turns as well. Pick one:
  - (a) a builder lane extends `LANDING_TOOLS` and its test, with the red test first
    (recommended)
  - (b) narrow the sentence to what the guard checks now

  Owning session: the coordinator, session_013NEJL2pASwRjgJDnsvnpNe.
