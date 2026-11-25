# Which tools an agent may call

## The ruling

- An agent never starts, messages, tags or archives a session. It never sets a scheduled task, or attaches a repo or a computer. The session that spawned the agent makes that call. Rule `agent-no-remote-tools` refuses such a call from an agent.
- An agent's call to an MCP tool that the `permissions.allow` list of settings.json does not cover is refused. Rule `agent-no-mcp-tools` refuses it. An agent cannot answer the permission prompt the call would raise, so the call would wait with no one to answer.
- An allow entry covers a call when it names the tool, its server, or a glob ending in `*`.
- For agents, the remote server's other tools pass: its read tools, and every tool outside the 20 outward names. The session's own calls pass.
- Seven roles withhold every MCP tool in their agent files: builder, test-author, record-writer, reviewer, Explore, Plan and refuter (`disallowedTools: mcp__*`). The designer and the design reviewer withhold the remote server only (`disallowedTools: mcp__claude-code-remote__*`), since they use the browser pane. Their other MCP calls still pass the allow list.
- The owner's typed override lifts either rule (`owner-override`).

Lane picks the owner may reverse:

- The lint checks every agent file, and requires the full MCP withhold in every role but the design pair.
- The remote read tools stay allowed for agents. `tests/guard/s29526-agent-remote-tools.py` pins them.

## The mistake

- Remote tools, 2026-11-07. A round-2 reviewer called `create_session`. It made an empty session, which was then archived. A test-author called `archive_session` with no target. The harness refused it. About 17:00 CST, an Explore agent in lane `replay-profile-parts` called `create_session`, and made a stray session.
- MCP tools, 2026-11-25. Each case had a brief that said to use no MCP tool, and none had an effect. About 17:00 CST, a consultant session's Haiku test-author called the iOS Simulator's detach and a preview listing, and another of its agents read a session-tool widget. The role lane's Haiku test-authors read the session start targets and an artifact, and one made a browser-pane call that the classifier refused. About 17:40 CST, the Sim Manager session's record-writer made a stray browser-pane script call. The owner's tasks that started the lane: fb-1407-1 and fb-1407-2 (2026-11-25 14:07 CST).

## The harm

- A stray or archived session.
- A message, a scheduled task, a repo or a computer acted on by an agent that no one briefed for that act.
- An MCP call that raises a prompt waits with no one to answer. The session that started the agent finds it only at a check-in (note `blocked-prompt-no-coordinator`).

## Why the agent files alone did not stop it

- An agent with no agent file held all 32 tools of the remote server. Measured 2026-11-07 15:42 CST. That covers the general-purpose agent and a Workflow `agent()` call with no `agentType`. The guard reads the `agent_id` key, not the agent file, so it also refuses an agent with no agent file.
- The check `session_tools_problem` in `lint/check_agent_models.py` reads the withhold line of each agent file. It does not block a call at run time.
- A brief's "use no MCP tool" line is prose only.

## The guard

- Rule `agent-no-remote-tools` (hooks/guard.py, rule 8b) refuses a call with a non-empty `agent_id` that names one of the 20 names in `REMOTE_OUTWARD_TOOLS` (hooks/shared_names.py). Those tools start, message, tag or archive sessions, set scheduled tasks, or attach repos and computers. The server has 32 tools (measured 2026-11-07 15:42 CST). Any non-empty `agent_id` counts, in any shape.
- Rule `agent-no-mcp-tools` (hooks/guard.py, rule 8c) refuses a call with a non-empty `agent_id` to an MCP tool that the allow list does not cover. The remote server is skipped there, because rule 8b judges its outward tools first.
- The allow list is read from settings.json: the install root's copy first, and the config folder's copy when the first cannot be read (`mcp_allow_entries`). Only `mcp__` entries count. When neither copy can be read, nothing is covered, so the call is refused. No test pins this.
- The PreToolUse matcher in settings.json (about line 269) ends `mcp__(?!ccd_session__start_session$).*`. The guard therefore starts for every MCP call except `ccd_session__start_session`.
- The guard stops a mistake, not an attacker (`guard-guards-mistakes-only`). The mistake is an agent that misreads its brief. That is why the guard exists (`building-guard-needs-incident`).

## Cost

- One guard process start per MCP tool call in every session, from the matcher above; this cost is unpinned.
- One settings.json read per agent MCP call that is not on the remote server, and a second only when the first copy cannot be read; this cost is unpinned.
- A refused call appends one line to `guard.log` (`refuse` in hooks/guard_core.py), and an allowed call writes nothing; this cost is unpinned.

Kind: process
Home: hooks/guard.py
Home: lint/check_agent_models.py
Home: settings.json
