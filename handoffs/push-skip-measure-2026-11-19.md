# Handoff: lane push-skip-measure (2026-11-19)

- Slug: push-skip-measure. Branch: none for work (nothing built). This file: archive/handoff-push-skip-measure.
- Open PRs: none. Agents started: none.
- Task: measure why main push runs skip so rarely (CI audit), then fix. Step 1 only.
- Done: measured the last 10 main push runs (REST). 1 skipped (43732993553, PR 3500, head tree = merge tree, head 0 behind main). 9 ran in full (PRs 3493, 3492, 3503, 3502, 3495, 3498, 3501, 3496, 3255): heads 5 to 41 commits behind main, so the merge commit tree matches no PR head tree; `decide()` at actions/push-skip/push-skip.py:272 is false. Gate works as designed. Tree mismatch is a silent `continue` (push-skip.py:246-247), so `main()` prints only `skip=false` (line 285).
- Could not read: the PR run's merge-ref tree; main movement between PR run and merge; push-skip job logs for the 9 runs.
- Unfinished: Step 2 (not built, by coordinator order 11:32 CST Nov 15). Option B (print one reason line on every run) was my recommendation; not started.
- Next step: none for this lane. Owner's page item 880 "Main push runs: what they test" (replaced 878) is open; consultant redrew it.
- Refused acts: none.
- Rulings held: coordinator, 11:32 CST Nov 15: do not build; push-skip reason already recorded (merge of #3502). Owner on item 878 (11:36 CST Nov 15): "none of these"; merge-needs-current-base may itself be wrong. No build grant.
- Receipt for 878: written by the coordinator.
- Scratch: /tmp/claude-0/-home-user-claude-settings/df9f172d-d17e-5aae-8559-2c54359e8dd2/scratchpad/m.py, n.py (reads only).
