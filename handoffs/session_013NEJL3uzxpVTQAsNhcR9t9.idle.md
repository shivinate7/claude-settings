# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL3uzxpVTQAsNhcR9t9

## Reply at 2026-11-10T17:28:30Z UTC

IDLE (B)
Goal (owner 2026-11-06 11:43 CST): a `claude -p` model call that cannot sign in is never quiet on any device or account. If a device needs a one-time setup, the owner is prompted for it there.
State: PR #1318 (model calls that cannot sign in are no longer quiet), branch model-call-auth-check, head 122a956b8, draft, not merged. All commits are pushed. Review round 1 failed with 6 findings, all fixed; round 2 passed; its notes 1-3 were fixed in a small change. Handed to batch runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) on 2026-11-06.
Built:
- SessionStart `decision_watch.py --auth-check`: silent when a token file exists. Otherwise one probe. Error kind AUTH (lost login) shows the `claude setup-token` fix; RUN shows "unknown" with the error. An off-shape reply stays silent.
- A run of 3+ failed calls in one session shows at Stop (stall_watch). Every invoke_model caller passes session_id.
Ruling recorded: coordinator 2026-11-06 13:57 CST, no probe when a token file exists, in decision `reply-judge-samples-never-refuses` (judge samples never refuse).
Left:
1. Rebase onto current main. The base is 4 days old, so conflicts are likely in hooks/decision_watch.py, settings.json and docs/catalog.md.
2. CI on the rebased head, then batch and merge.
3. The local lint run skipped 12 PR-only steps, so CI must run them.
Files: hooks/decision_watch.py, hooks/stall_watch.py, settings.json, hooks/test_model_auth.py, and the callers (call_judge, reply_judge, feedback_guard, prose_judge, sendmessage_state, override, lint/report_guard).
Answers already given: the owner note (cloud works with no setup; Mac needs state/hook-token; API key needs an allowlist change) went to the coordinator on 2026-11-06. The answer on the Mac sign-in race went to triage for page item 300.

