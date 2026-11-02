# Handoff: lane rotation-text-current

Wound down on the coordinator's word (owner instruction, 2026-11-02 12:31 CST). The lane session
was session_013NEJL29orzrmWAKpvEAjyn; the coordinator is session_013NEJL2pASwRjgJDnsvnpNe.

## Goal

Make the project-ops skill match decision `session-tiers`, "Rotation of standing sessions": no usage
limit (owner, 2026-11-01 17:56 CST, waiting item 109, pick b). A standing session (triage, batch
runner, arbiter) runs until autocompact and rewrites its handoff at each compaction. The coordinator
rotates one only when it goes stale or breaks.

## Rulings in force

- `session-tiers` line 16, as above. Cite it by slug; copy none of its text (owner, 2026-11-02 10:41
  CST; lane child-rules-cite-records writes that rule).
- Coordinator, 2026-11-02 12:39 CST: keep the template's `get_session` `context_usage` read, with
  no limit; leave the self-reported tally unchanged until the owner answers the open question below.
- speak-rewrite-superseded-in-place, outcomes-decision-is-argument, building-one-home-per-capability.

## State

- Branch `rotation-text-current`, from main 74be1279. No PR yet.
- 9915deb4 (test-author): skills/project-ops/tests/test_scaffold.py. Re-points the two limit asserts
  and adds red cases. Red on 74be1279: 12 failed, 44 passed. Each fails because the old text is
  still there; product code is unchanged. The red ran in the agent's own worktree, because the guard
  refused a separate red-run checkout.
- This file. Nothing else is unpushed.

## Next step

A builder (record-writer, Markdown only) edits these until the tests go green:

1. skills/project-ops/SKILL.md line 3 (also the trigger text) and line 17: drop "usage tally".
2. skills/project-ops/templates/operating-model.md, "## Rotation of standing sessions":
   - Name the arbiter with triage and the batch runner.
   - Say a standing session runs until autocompact, and rotates only when it goes stale or breaks
     (cite `session-tiers`).
   - Drop the limits line, "at its limit, at a phase change", and the exemption line.
   - Keep steps 1-5 numbered as now. Step 3 must stay the hand-off file step that names
     check_handoff.py; the tests index it.
   - Keep the `context_usage` read, with no limit.
3. skills/project-ops/templates/roster.md line 15: drop the `Exemptions:` line.
4. README.md line 289: drop "by a usage tally".
5. Run `python3 lint/hook_catalog.py`; docs/catalog.md line 79 copies the SKILL.md description.

Then a reviewer reads the diff. Then the lane lint:
`~/.claude/bin/verdict ~/.claude/bin/ci-job checks --lint`,
`python3 lint/check_silent_undo.py --upstream origin/main --head HEAD --strict`,
`~/.claude/bin/merge --lane-lint <pr>`, and `python3 -m pytest skills/project-ops/tests -q`.
Then open a draft PR and send its number, head and review verdict to the coordinator and to the
batch runner.

## Task 3: child repos

On main and on each record branch of home, degen, banchi, q_max, joyous, mailaudit and ios-adblock,
git grep found no copy of the old rotation text. The operating model is pasted into each claude.ai
project's instructions. This session cannot read those, so they are unknown, not clear. Home, degen
and mailaudit have a `roadmap` record branch, a sign that they adopted project-ops. After the merge,
each of those three repos needs a brief: its coordinator re-pastes the new rotation section from
operating-model.md, at the merge sha, into its project instructions. No brief is written yet.

## Open questions

- Owner, through the coordinator: drop the self-reported tally? `session-tiers` line 16 still has
  standing sessions report one. Line 18 says dropping it needs the owner's grant. Nothing on main
  reads it now. Recommended: drop it. Does not block the lane.
- Coordinator: `session-tiers` line 136, "Open: the context limit for each tier", is stale under
  item 109. Lane child-rules-cite-records owns that record.

## Deviations

- The test-author ran Haiku 5.5, not Sonnet as `agent-model-cap` sets; its commit says so.
