# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJKz785dJ3UKyxpvQuZu

## Reply at 2026-11-10T17:23:23Z UTC

IDLE (B) — lane handoff-per-agent (session_013NEJKz785dJ3UKyxpvQuZu). Nothing running, nothing unpushed.
Goal: an agent never writes its parent session's handoff (coordinator brief, 2026-11-07), plus two follow-up steps the coordinator sent: handoff-bash-redirect and builder-checkout-test-path.
State: all 3 PRs are open and released to batch runner 8 (session_013NEJL2vsmyKzJm8jUDt6za). Each has a tool review record for its head:
- #1679, lane/handoff-per-agent, head ab723cdd5. New guard rule agent-handoff-write stops an agent's file-tool write of the handoff. run_precompact skips writes in an agent worktree. Decision precompact-handoff, item 14.
- #1714, lane/handoff-bash-redirect, head b032ff039, stacked on #1679, so merge it after #1679. The same rule also reads shell and interpreter writes.
- #1732, lane/builder-checkout-test-path, head 6273a1a08, independent. Rule builder-test-edit now refuses a builder's `git checkout <rev> -- <test>` and `git restore --source`, including folder specs.
Left:
- The runner merges the three PRs.
- On a lane-lint drop: merge main in, fix form only, get a fix check, then post the tool's record.
- Gaps open in item 14: dd, `>|`, a `(cd …)` subshell, `[IO.File]`; a no-worktree agent's PreCompact state write. `Fix: none … Until: 2026-11-21`.
Files: hooks/guard.py (agent-handoff-write, builder_shell_test_hit, git_source_test_hit), hooks/precompact_handoff.py (run_precompact), hooks/reread_check.py (names_handoff), hooks/guard_shared_tree.py (split_dashed, source_pathspecs), docs/decisions/precompact-handoff.md item 14.
Handoff file: ~/.claude/handoffs/f5ba0448-87b5-5d56-9b15-3e13cf153513.md.

