# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL2ZJUtVxqpKrEjh7X2

## Reply at 2026-11-10T17:27:16Z UTC

IDLE (B). Lane sim-tool-lease-check. No agent or command of mine is running.
Goal: roadmap step sim-tool-lease-check. The iOS Simulator MCP tool must refuse a call on a device whose live sim-lease the caller does not hold (incident 2026-11-08, 10:43-10:50 CST).
State: PR #2256 (draft), branch sim-tool-lease-check, head 8c74fbbf4cf4a382dfa94d09c69b31ca5e3dbc11, everything pushed. It is stacked on #2231 (lane-sim-hold-path): "Merge after: #2231". It was handed to runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) on 2026-11-08. The review record is posted on the PR: rounds 1 and 2 FAIL, round 3 PASS (reviewer sonnet), net value positive.
What it adds: guard rule simulator-device-lease (hooks/guard.py); `sim-lease take --for-udid` (bin/sim-lease); sim-test takes a lease on reuse and exits 1 when another live holder keeps the slot (bin/sim-test). It rewrites decisions sim-test-is-the-one-boot-path and sim-lease-tool, and adds three notes to docs/debts/notes.md.
Tests: hooks/test_guard.py (simulator family), lint/test_sim_lease.py, lint/test_sim_test.sh, hooks/mutate_guard.py anchors.
Left: CI on the integration run, then the merge after #2231. Possible conflict in hooks/mutate_guard.py: this lane re-pointed the live-stream and waiter anchors that #2231 had left stale. Guard gaps queued with the coordinator: step:resume-needs-live-worktree, step:brief-no-checked-out-branch. The roadmap step status is still to be set.

