# Handoff: lane cloud-snapshot-age-check, 2026-11-19

Slug: cloud-snapshot-age-check. Session: session_013NEJL3nsbMvrAgxfXv4x51. Parent: coordinator session_013NEJL1gw6EdrSyvHkTUEx6. Hand-in target: runner 10, session_013NEJL2f1YCYsvLdpFqtWP3.

Goal: the start hook warns once when a cloud snapshot's settings.json still holds a startup entry other than the refresh hook, and names the fix (edit the environment, save the Setup script). hooks/ lag alone does not warn (decision cloud-start-hooks-run-fresh). Owner pick 744 b, 13:2x CST Nov 13: start the step.

## Open PR

- #3370, draft, open. Branch `cloud-snapshot-age-check-v4`. Live head read at 00:26 CST Nov 19: `1448bd8a926adb5cb7013230f7e619cbeffee255`. Base main.
- The head moved after my last hand-in. My last head was `ad3f64ec351cffe1f5aec9180373a7d96b5cf58b`. A later session that carries my session link pushed two commits on Nov 15 (18:49 to 18:56 CST): a drop of two duplicate notes, and a merge of main that resolved the `hk_envrun` hunk in hooks/test_install_src.sh. Its lane-lint comment reads PASS on `1448bd8a92`, and a review record on that head holds round 1 haiku FAIL, round 2 sonnet PASS and a Fix check (sonnet PASS at `ad3f64ec35`). I did not make those two commits and have not read them.
- Older PRs of this lane, closed and replaced: #1363 (old lane, closed before this lane), #3246, #3263.
- Not marked ready. Only the batch runner marks ready.

## Done

- Rebuilt the old lane's 8 commits on main (the old branch had 38 conflicts).
- Round 1 on the live head found a real regression from the merge with main: with no stable branch on origin the refresh hook named stable. Fixed with case `caseK16`, red first.
- Re-pointed `hk_envrun` so snapstale10 and snapstale11 run at their pinned ref. A scratch mutant went red on both.
- One home for the refresh fetch text: `REFRESH_FETCH` in install.sh.
- Fixed the reader `installer_forms()` in hooks/test_auto_mode_allow.py (the Coordinator's bisect found 5 failures on main plus this PR).
- Notes filed in docs/debts/notes.md (five snapstale notes, no duplicates of stable's notes).

## Unfinished

- Merge of #3370. Runner 10 holds it; the Coordinator sends the go.
- Review round record: a record exists on `1448bd8a92`; I did not confirm the live head has not moved since 2026-11-16 04:44 CST.
- Gap for triage, not queued: touched-tests did not select hooks/test_auto_mode_allow.py though it reads install.sh's text. A map from a file to the tests that read its text would have caught the miss.
- Unmeasured: whether the cloud SessionStart hook env sets `CLAUDE_PROJECT_DIR` (decision cloud-start-hooks-run-fresh; a note in docs/debts/notes.md).
- Comment on install.sh line 24 area ("Resume stays silent") holds only for a readable source; left as is.

## Next step

Read #3370's live head and checks. If the Coordinator wants it merged: runner 10 runs the merge tool on the named head. If the head moved: `merge --lane-lint 3370`, then re-print the review record at the live head.

## Refused acts and overrides

None. No override line was printed. `--lint-unknown-ok` was not used (Coordinator, 16:30 CST Nov 13: no).

## Owner rulings held

- Owner pick 744 b, Nov 13: start cloud-snapshot-age-check and c107. Filed by triage in roadmap ruling own-744-b-start-both. Inbox item `fb-1324-1` is `not-a-grant` (a relayed task assignment, no act rests on it).
- Standing grant: lane draft PR (owner, 2026-11-12 17:19 CST). The lane may open its own draft PR and never marks it ready.
- c107 stays open for the Mac probe only (triage, page item 751). This lane wrote no c107 decision.

## Agents of this lane (all finished; their worktrees are gone)

- reviewers: round 1 haiku on head `b94171bb7` (PASS); round 1 haiku on `ad77a83cf` (FAIL, regression); fix verifier sonnet on `03761b771` (PASS); round 1 haiku on `ddc8422266` (FAIL, two findings); round 2 sonnet on `67d9184183` (PASS); fix verifier sonnet on `05c9de6b96` (PASS).
- builder and test-author roles: this session, no separate agents.
- worktree of this session: `.claude/worktrees/snapshot-age` (branch `cloud-snapshot-age-check-v4` last); this handoff: `.claude/worktrees/handoff-snapshot`.

## Branches

- `cloud-snapshot-age-check-v4` (#3370, live)
- `cloud-snapshot-age-check-v3` (#3263, closed, kept on origin)
- `cloud-snapshot-age-check-v2` (#3246, closed, kept on origin)
- `cloud-snapshot-age-check` (old lane branch from #1363)
