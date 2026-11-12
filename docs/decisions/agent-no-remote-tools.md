# An agent never calls a session-acting remote tool

## The ruling

- An agent never starts, messages, tags or archives a session. It never sets a scheduled task, or attaches a repo or a computer. The session that spawned the agent makes that call.
- The `agent-no-remote-tools` rule refuses such a call from an agent. Read tools pass. The session's own calls pass.
- The owner's typed override lifts the rule (`owner-override`).

## The mistake

Agents called claude-code-remote tools. Those tools act outside the session. Three cases, all 2026-11-07:

- A round-2 reviewer called `create_session`. It made an empty session, which was then archived.
- A test-author called `archive_session` with no target. The harness refused the call.
- About 17:00 CST, an Explore agent in lane `replay-profile-parts` called `create_session`. It made a stray session.

## The harm

- A stray or archived session.
- A message, a scheduled task, a repo or a computer acted on by an agent that no one briefed for that act.

## Why the agent files alone did not stop it

- Each agent file withholds the server with `disallowedTools: mcp__claude-code-remote__*`. The check `session_tools_problem` in `lint/check_agent_models.py` requires that line.
- An agent with no agent file held all 32 tools of the server. Measured 2026-11-07 15:42 CST. That covers the general-purpose agent and a Workflow `agent()` call with no `agentType`.

## The guard

- The guard refuses a call that carries a non-empty `agent_id` and names a tool in `REMOTE_OUTWARD_TOOLS`. The tuple holds 21 names: 20 of the server's 32 tools, and `start_session` of the session server (`mcp__ccd_session__start_session`, named once as `START_SESSION_TOOL`). These are the tools that start, message, tag or archive sessions, set scheduled tasks, or attach repos and computers.
- The guard reads the key, not the agent file. So it also refuses an agent with no agent file.
- Any non-empty `agent_id` counts, in any shape.
- The guard stops a mistake, not an attacker (`guard-guards-mistakes-only`). The mistake is an agent that misreads its brief. That is why the guard exists (`building-guard-needs-incident`).

Kind: process
Home: hooks/guard.py
Home: lint/check_agent_models.py
