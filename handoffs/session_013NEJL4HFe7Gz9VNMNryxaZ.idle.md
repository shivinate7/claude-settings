IDLE (B): lane report-model-from-role (session_013NEJL4HFe7Gz9VNMNryxaZ). Checked 11:29 CST.
Goal: the model-name report guard (rule reports-done-names-models) skips role words in code spans and reads each agent's served model.
State: all PRs are open drafts, handed to batch runner 8 (session_013NEJL2vsmyKzJm8jUDt6za), with merge-tool records for live heads. Nothing unpushed, nothing running.
- #1705 lane/report-model-from-role-2 @ 60aca2fb5 (stacks on #1638 @ 57b18a3c3 and #1643 @ 379eb58d4)
- #1716 step/mask-spans-gloss @ 62a42b2ae
- #1721 step/next-waiver-scope @ 8701b1fc9
- #1727 step/next-waiver-followups @ 89c5c3e49
Merge order: #1638, #1643, #1705, #1716, #1721, #1727.
Left: queued follow-up, not started. Once #1917 and #1727 are on main, switch report_guard running_spawns to _transcript.agent_state, with unknown mapped to finished.
Files: lint/report_guard.py, lint/word_runs.py, hooks/shared_names.py, hooks/stall_watch.py; tests lint/test_report_guard.py, lint/test_word_runs.py, hooks/test_stall_watch_stop.py.
