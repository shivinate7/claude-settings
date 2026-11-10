# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL3kYhJPjjsWYNCApSh

## Reply at 2026-11-10T17:28:14Z UTC

IDLE (B). Lane artifact-guard-matcher-names: guards for the artifact tools also fire on Mac `mcp__claude-artifacts__*` calls.
Goal: every guard that covers the artifact tools also checks the Mac names (owner item 434) and their input shapes (owner item 440).
State: PR #2279, branch lane/artifact-guard-mac-names, head 8bc720ad0, draft. Released to batch runner 8 on 2026-11-08. Review record posted (comment 6727831626): round 1 FAIL (haiku), rounds 2-3 PASS (sonnet), net value positive, fix check PASS. Lane lint PASS at 8bc720ad0. Nothing is unpushed. No agent or command is running.
Files: hooks/shared_names.py (cloud_twin and the Mac name sets), hooks/guard.py, hooks/call_judge.py, hooks/local_time.py, lint/_transcript.py (cloud_use), hooks/feedback_guard.py, lint/report_guard.py, settings.json (exact Mac names on three matchers), hooks/mac_artifact_shapes_test.py plus the Mac cases in test_guard, test_call_judge, test_feedback_inbox, test_waiting_export, test_report_guard, test_settings_matcher and test_shared_names. Notes in docs/debts/notes.md (d18b5e0a8).
Left: (1) runner 8 batches and merges #2279. Its base is 422cbbdfe and main has moved far since, so it may need a rebase and a fresh lane lint. (2) The old branch lane/artifact-guard-matcher-names is still on origin, with a copy at archive/lane/artifact-guard-matcher-names. #2275 is closed. Delete the old branch under the cloud-refused standing grant. (3) Open debt and notes: report-guard-url-string-compare, extended to Mac writes; mac-write-drops-file-path; mac-publish-asset-fallback.

