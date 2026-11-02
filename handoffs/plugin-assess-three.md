# Handoff: lane plugin-assess-three

Lane session `session_013NEJL4F6AQcHRyHCWa7re4`. Coordinator `session_013NEJL2pASwRjgJDnsvnpNe`.
Written 2026-11-02 12:55 CST, on the owner's wind-down instruction (12:31 CST).

## Goal

Assess three catalog plugins, iceberg, Ambition Lenses and Hypotize, and say whether to add each.
Then design a trial that compares lane outcomes with and without Ambition Lenses.

## Owner rulings

- 2026-11-01 21:32 CST: "send a lane to assess" the three plugins. Assess only, install nothing.
- 2026-11-01 22:27 CST: "we need to see which is better, we can't just assume I'm right". Compare
  outcomes, not rules.
- 2026-11-01 22:43 CST: run the Ambition Lenses trial.
- iceberg and Hypotize: skip. This is the lane's pick, given to it by the coordinator at 23:42 CST,
  because no install is the state on `main`. Adding either needs the owner's grant.
- 2026-11-01 23:08 CST (coordinator): reach 8 cases with shadow pairs on the next five lanes.

Home of each: the "Ruling" section of `docs/plans/plugin-assess-three.md`.

## Branch and PR

- Branch `plugin-assess-three`, head db760690109c84f9ac1aa277ecaec707faca2c16 before this handoff.
- PR #1036 (plans: assess three catalog plugins), draft. No review rounds: it is a record, docs
  only. It stays a draft until the trial has results.
- Files: `docs/plans/plugin-assess-three.md` and three briefs in `docs/plans/trial-briefs/`.
- The PR title and body still say "skip all three". The record holds the current ruling. The next
  session updates the title and body.
- Local `ci-job checks --lint` is red only on the hook catalog, which wants a `docs/records.md`
  row. Decision `records-index-at-merge` says a lane never commits that page and PR CI waives it.

## Done

- The assessment: sources read at pinned commits, with cost, overlap, rule conflicts and a verdict
  per plugin.
- Outcomes compared on six incident cases: ours better in 3, the plugin in 1, 1 tie, 1 unknown.
- The trial design: arms, a fixed primary measure and win rule, blind reviewers, and a spawn list
  of 7 runs. A Sonnet bias audit rated the first draft "fair with fixes", and all ten fixes are in.
- The shadow-pair rule for the next five lanes.

## Next step

- The coordinator started the 7 runs at 23:08 CST. Their results and scoring belong to the
  coordinator. This lane holds no run state.
- When 8 cases have scores, write the result into the record, settle the Ambition Lenses verdict,
  update the PR title and body, and hand the PR to the batch runner.

## Open questions

None owned by this lane.

## Not pushed

Nothing. Scratch files in this session's scratchpad (case notes and cloned plugin sources) are
working copies only. The record holds everything they found.
