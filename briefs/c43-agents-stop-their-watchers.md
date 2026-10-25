# c43. Agents stop their watchers before they report

Paste this whole file into one fresh claude-settings session. Written by the advisor, Oct 25,
against claude-settings main f463787.

## The defect (verified, not assumed)

Claim from the Degen orchestrator, Oct 25: a subagent arms watchers (Monitor, or Bash with
run_in_background) on a long test run, reports early, and never stops them. Each watcher later
ends, wakes the finished agent, and sends the parent a new task notification. Seen: one Degen
reviewer woke 4 times after its final report.

Reproduced by the advisor, Oct 25, in a Claude Code cloud session: a subagent armed a Monitor
(timeout 60 s) and a background Bash (sleep 90 s), then sent its final report at 8 s without
stopping either. The parent got three task notifications for that one agent: at 8 s (the report),
66 s (the monitor's expiry woke the agent; it replied) and 96 s (the background task's end woke it
again). The notice on the first two said "waiting on its own background work". Desktop app
behaviour: not checked, assumed the same (same harness).

What the agent's transcript holds (subagents/agent-<id>.jsonl, the file the SubagentStop input
names): each start's tool result names its task id ("Monitor started (task <id>", "Command running
in background with ID: <id>"); TaskStop calls carry task_id; each end arrives as a user entry
starting "[SYSTEM NOTIFICATION" that names the task id.

## Lane 1, the rule (one sentence per file)

In agents/builder.md, reviewer.md, test-author.md and record-writer.md (any agent that runs long
checks; check explore.md and plan.md too), next to the existing "before you stop" sentence, add one
sentence in that file's style: before the final report, stop every Monitor and background task you
started with TaskStop, and start none after it.

## Lane 2, the check (only if the hook input allows it; prove it first)

Home: judge_stop in hooks/guard.py, which already runs on SubagentStop. Extend it; build no second
hook. Incident for building-guard-needs-incident: the Degen reviewer, Oct 25.
- Read the agent's transcript (the SubagentStop input's agent transcript path; confirm the field
  name from a real payload first, and stop and report if no field names it).
- Live tasks = ids started by a Monitor or a run_in_background Bash, minus ids passed to TaskStop,
  minus ids named in a later end notification.
- Any live task and stop_hook_active false: block the stop once (decision block), reason naming
  each live id and "stop them with TaskStop, then report again". stop_hook_active true: never block
  again; log a noted line (rule id agent-live-tasks) and let it stop. An unreadable transcript is
  no finding (fail open: this is hygiene, not a safety guard).
- Cost, per outcomes-mechanize-rules: no process start; one read of the agent's transcript per
  agent stop; no file written except one guard.log line on a finding. A test pins it.
- Proof: test-author writes cases red on main: a fixture transcript with a Monitor started and
  never stopped blocks once; the same with TaskStop passes; one whose task's end notification
  arrived passes; stop_hook_active true with a live task passes and logs one line; an unreadable
  transcript passes. Builder makes them green. Then one live run: spawn an agent that leaves a
  60 s Monitor and report what the parent saw (one notification, not two).

## Review and merge

A reviewer reads the diff (it adds a gate verdict). Usual rules: git-integration-branch-merge,
roles-review-cap-three. Report: Done, Deviations, Decided by the advisor, Input Needed, Next.
