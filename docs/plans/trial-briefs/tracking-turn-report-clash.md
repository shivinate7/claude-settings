Lane brief: tracking-turn-report-clash. You are a lane session (one lane, Opus). Coordinator: session_013NEJL2pASwRjgJDnsvnpNe. Batch runner 6: session_013NEJL3AqQUisjbiTcrCECQ.

Owner incident 16:18-16:23 CST, recurring since Sep 23 (#125, #669, #706): the report guard forces a second message. The cause is two rules that clash. Rule output-tracking-turn-one-line wants one line on a turn that only tracks work. lint/report_guard.py wants the full report on any turn that commits, pushes or merges.
Read the step: `git fetch origin roadmap && git show origin/roadmap:roadmap/data/steps/tracking-turn-report-clash.json`.
Task: as the step says, one sentence in output-styles/shiv-stylisms.md that settles which rule wins on a turn that lands something. Keep the guard's verdict as it is unless the step says to change it. If the step calls for a guard change, it goes to a builder with a red test first.
Agents: record-writer (haiku), reviewer round 1 (haiku). Rounds 2-3 run sonnet, with `Round N of 3` as the brief's first line.
Rules: never EnterWorktree, confirm_repository_trust, request_computer_folder or create_session. Writing agents use Agent isolation 'worktree' and name their model. Run `~/.claude/bin/verdict ~/.claude/bin/ste-changed origin/main`.
Done: a draft PR on branch tracking-turn-report-clash, handed to the batch runner. Report to me in 10 lines or fewer.
