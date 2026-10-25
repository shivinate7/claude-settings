# A stop with a live background task is blocked once

## The ruling

Request, 2026-10-25: an agent that stops with a background task still running is told to stop it first.

- The guard rule `agent-live-tasks` is in `hooks/guard.py` (`judge_stop`, `live_tasks`). It runs on SubagentStop for every agent role. The diff judgement of a builder, test-author or record-writer is unchanged.
- The agent's own transcript is the source: the payload field `agent_transcript_path`. `transcript_path` is the parent's and is never read.
- A task is live when its start is seen and no later line ends it:
  - Start: a Bash or PowerShell `tool_result` that begins `Command running in background with ID: <id>`, or a Monitor `tool_result` that begins `Monitor started (task <id>,`. Text a foreground command prints does not count.
  - End: a `TaskStop` call with that `task_id`, or a later `task-notification` entry whose `<status>` is terminal (completed, failed, killed, stopped, cancelled, terminated, expired, timeout, error, exited). A Monitor event notice has no terminal status and ends nothing.
- With a live task and `stop_hook_active` false, the stop is blocked once. The reason names each live id and says to stop them with TaskStop, then report again.
- With `stop_hook_active` true, the stop passes and the guard writes one `agent-live-tasks` line to `guard.log`.
- Fail open: a transcript that is missing, unreadable or not JSON gives no finding.

Why: a Degen reviewer woke its parent four times after its report, once per background task end (2026-10-25). The advisor reproduced three notices from one agent. Each wake costs the parent a turn.

Risk kind: incident, per `building-guard-needs-incident`. Landed 2026-10-25.

Cost, per `outcomes-mechanize-rules`: process starts, none. Files read, one: the agent's transcript, once per agent stop, through `lint/_transcript.py` `read_transcript`. Files written, none except one `guard.log` line on a block or a second stop. How often: once per agent stop. No timer, no watcher. `hooks/test_guard.py` (family `diff`, cases `live-tasks:`) pins one transcript read, no extra child process and one `guard.log` line.

Side change: `record` in `hooks/guard_core.py` makes the config folder only when it is missing, so a log write into an existing folder makes no directory call.

Kind: process
Home: hooks/guard.py
