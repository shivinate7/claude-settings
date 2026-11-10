# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL2B1oRJaBTe16wm1VG

## Reply at 2026-11-10T17:26:42Z UTC

IDLE (B). Lane spawn-model-cap-all-roles.
Goal: the spawn guard applies the model cap to every role (coordinator brief, 2026-11-07 15:05 CST).
State: PR #1638 (model-cap fix), branch spawn-model-cap-all-roles, head 57b18a3c3, fully pushed. It is an open draft on base main 174b005c1, handed to batch runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) on 2026-11-07 at 17:05 CST. It is not merged, and it likely needs a rebase onto the current main.
It holds three parts, each with a positive net value at review round 3:
1. hooks/guard.py agent-role-model: a no-model Workflow agent() is refused when no default model is set, and "inherit" counts as unset.
2. hooks/guard.py roles-third-round-steps-up: a SendMessage carrying `Round 3 of 3` to a builder not on Opus is refused. settings.json adds SendMessage to the guard matcher.
3. lint/report_guard.py model-name check: Done pairs are matched across the whole transcript, "design reviewer" is no longer read as reviewer, and a running role named under Next is waived.
Also on the PR: hooks/mutate_guard.py anchors, docs/decisions/agent-model-cap.md, docs/debts/done-models-next-waiver-loose.md, and 8 notes in docs/debts/notes.md (each Fix: none, Until 2026-11-21).
Left: rebase onto main, then the batch CI run and the merge (runner 8). docs/records.md is left for the merge tool.
Handoff file: /root/.claude/handoffs/9ec9bee4-b262-57b2-b301-a7a95b5b23ab.md

