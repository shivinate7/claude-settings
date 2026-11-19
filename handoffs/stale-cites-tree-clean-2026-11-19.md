# Handoff: lane stale-cites-tree-clean (2026-11-19, 00:3x CST)

Lane of coordinator session_013NEJL1gw6EdrSyvHkTUEx6. Role: lane (decision session-tiers). Repo: shivinate7/claude-settings.
Step record: branch `roadmap`, `roadmap/data/steps/stale-cites-tree-clean.json`. Done means: `python3 lint/stale_cites.py --tree` passes on main.

## State
- Check on origin/main bd0759f83c at 2026-11-19: FAIL, 182 findings (was 158 on 2deb827ad when the lane started; main gained more).
- Lane fixed 114 of the 158, prose only, in four branches, each passed `merge --lane-lint`. None merged.

## Branches and PRs (REST, read 2026-11-19)
| Branch | Head | PR | State |
|---|---|---|---|
| stale-cites-plans | a77d54fdee | #2803 | open, draft (68 findings, docs/plans) |
| stale-cites-decisions | 071d2bf493 | #2804 | open, draft (17 findings, 13 decision files) |
| stale-cites-design-debts | ee9ad636c4 | #2805 | open, draft (18 findings, design notes and 4 small debts) |
| stale-cites-janitor-skills | 3971c8ede1 | #2807 | closed unmerged (stale: conflicted with main) |
| stale-cites-janitor-skills-2 | e9882df8c6 | #3165 | closed unmerged by triage 2026-11-15 18:37 UTC under its stale-drafts rulings ("silent 24 h or more, not proven dead") |

All five branches are pushed on origin. Bases: the first four on 2deb827ad; the -2 branch on main of 2026-11-13. #2803-#2805 were not rechecked against newer main.

## Agents (all finished, none running)
Record-writers, each in its own worktree under /home/user/claude-settings/.claude/worktrees/: ab2254ff932766865 (plans, branch worktree-agent-ab2254ff932766865 = stale-cites-plans head), a661eef4201247936 (decisions), a1c6efd6e5feb36ed (design-debts), a2281f6ba47d68b87 (janitor-skills). The reports said haiku 5.5; I named no model.

## Unfinished
- 44 findings were held in files that open lanes touched (docs/debts/notes.md 29, README.md 6, six decision files, skills/ios-apps 2, skills/ci-hygiene 1). Coordinator pick, 2026-11-12: wait for those lanes to merge, then a second pass. Not started.
- The janitor/compliance-check fix needs a new PR on current main (#3165 was closed). The edit is commit e9882df8c6 (cherry-pick of 3971c8ede1; conflict in skills/compliance-check/probes.md resolved by keeping main's hooks row).
- 182 findings now: re-run `stale_cites --tree` before any pass; the held-file list above is old.

## Next step
1. Re-run the check on current main; sort findings by folder against open PRs' files.
2. Rebase or rebuild #2803-#2805 on current main; reopen or open fresh draft PRs; lane lint; hand to the runner through the coordinator.
3. Second pass for held files.

## Notes and refused acts
- Flaky test seen: `ShardTests.test_no_shard_runs_all` (list order) failed lane lint once, passed on rerun. No note filed.
- `debate-model-tiers.md` uses "Critic:" where the check reads "Refuter:"; coordinator sent it to triage as a note.
- Refused once: an Agent spawn with a `model` field (guard agent-role-model, remedy: drop the field; done). No push or other act was refused.
- Check was never changed or weakened. No false alarm in the check found.

## Owner rulings held
None of my own. Coordinator picks: wait-then-second-pass (2026-11-12); rebuild #2807 per backlog-drain ledger (2026-11-13).
