# Handoff: lane agent-end-read-in-hook (2026-11-19 00:25 CST)

- Slug: agent-end-read. Branch: none built. Head: none. Open PRs: none from this lane.
- Step: opus-ask-grants-one-spawn (roadmap branch). Ruling held: own-761-d-task-scoped-opus (a plain Opus ask lifts only its own spawns; ends when they end).
- Agents spawned: none.

## Done
- Step 1 (measure), read only. Asked lane owner-override-one-route (session_013NEJL1ymdMFYoj4wQG9oUR) for the captures.
- That lane did not run the 29-of-60 count; its Plan agent did. Its fresh count: 44 of 93 SubagentStop events list the stopping agent as running.
  - Field: payload `background_tasks[]` entry (`type: subagent`, `status: running`) whose `id` equals payload `agent_id`.
  - Source: hook payload written by the settings.json SubagentStop row (`janitor/agent_end_reap.py`).
  - File: `/root/.claude/state/agent-end-payloads.jsonl` on that lane's container, not git, last 200 lines. Absent in this lane's container.
- My recount: unknown. Stale-at-stop versus still-finishing: unmeasured.
- First report sent to coordinator after step 1.

## Unfinished
- Step 2 design and step 3 build, not started.

## Next step
- If the 44-of-93 count holds, the hook cannot tell reliably that an agent ended. Do not build around it.
- Smallest honest alternative: end the grant at the owner's next typed prompt (the local_time hook already reads it), as draft #2928's interim end does, without its agent-end half. Draft #2928 head 81231d70a319, #2850: not edited.
- To confirm the count first, get the 93 lines (or one sample) readable by a session.

## Refused acts
- None. Inbox items fb-1836-1 and fb-1836-2 filed in `/root/.claude/handoffs/802d5e65-4937-5bde-aeef-f37d13ae62e5.inbox.md`.
