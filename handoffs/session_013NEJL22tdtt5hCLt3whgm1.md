# cloud-bin-on-path (session_013NEJL22tdtt5hCLt3whgm1), received 09:55 CST 2026-11-10, kind B

Handoff (B), lane cloud-bin-on-path (session_013NEJL22tdtt5hCLt3whgm1):
1. Work: step cloud-bin-on-path: ~/.claude/bin on PATH in cloud installs, so bare wait-pid and verdict stop failing with rc 127.
2. Repo shivinate7/claude-settings, branch worktree-cloud-bin-on-path (pushed, nothing unpushed), draft PR #2528, head 55c36287119648c36f2b6cc0161b8cbc7ff1280e.
3. State: review record posted (comment 6767218976; rounds haiku FAIL, sonnet FAIL, sonnet PASS; net value positive). Install suite on head: exit 0. `merge --lane-lint 2528` UNKNOWN at the 1200 s cap, no failed step. Not released to the batch runner; not merged.
4. Left: batch runner takes the PR. Three notes unfiled (symlinked-rc and failed-write test gap; guard_stream.py lines 73, 559, 728 still print bare `bin/wait-pid`; PATH block goes in the rc of $SHELL only, unmeasured whether the cloud Bash tool reads it).
