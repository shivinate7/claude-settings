# A refused tool call reaches the owner

## The ruling

Owner-side goal: when the auto-mode classifier refuses a tool call, the owner hears of it in the session's reply. A session may not keep a refusal only in its handoff.

- `hooks/refusal_note.py` runs on the PermissionDenied event. It adds one line, `{ts, tool_name, reason, tool_use_id}`, to `<config dir>/state/refusals/<session_id>.jsonl`.
- A reason that starts with "Auto mode could not evaluate this action" or "Classifier unavailable" is a classifier outage with no verdict. The hook writes nothing for it. "Starts with" is literal: a reason that only holds the phrase is a real refusal.
- The row also carries `agent_id` when the payload names an agent. A row without `agent_id` is the main session's.
- A tool that is already pending in the file is not added again. A row with `agent_id` does not count as pending, so an agent's refusal never hides the main session's refusal of the same tool. The hook skips a line that is not JSON when it reads the file, so a bad line never stops a new refusal being recorded.
- The hook prints nothing, never prints `retry`, and exits 0 on every path. The event reads only `retry`, and ignores the exit code and stderr (https://code.claude.com/docs/en/hooks#permissiondenied).
- `lint/report_guard.py` reads the file at every Stop, landed or not. A pending tool that the reply does not answer blocks the Stop. The reason quotes the tool's full name in backticks, so one rewrite that answers it clears it. It asks for an Input Needed line "allow `<tool_name>`?" and a line in `docs/debts/notes.md`, or one line "`<tool_name>`: refusal was right".
- Each tool that the reply answers leaves the file. An answer is the tool's name under Input Needed, or one line, anywhere in the reply, that names the tool and says "refusal was right" or "refusal is right". The rest stay pending. The file goes when none is left.
- A Stop with `stop_hook_active` set never blocks on a refusal. It still clears each tool its reply names.
- A name outside Input Needed is no answer, except on a line that says "refusal was right" or "refusal is right". That phrase without the tool's name on the same line answers nothing.
- An agent's refusal is not the session's. `lint/report_guard.py` drops a row when it has `agent_id`, or when its `tool_use_id` is a tool_use only in a sidechain: a sidechain record of the hook's transcript, or a record in `<session>/subagents/agent-<id>.jsonl` beside it (measured on a real session's transcripts). A row stays when its id is in a main record, is found nowhere (the transcript may not have flushed the call, and a refusal must not be lost), is absent, or the transcript cannot be read.
- A built-in tool such as `Edit` or `Bash` is named only in backticks, because a bare "Edit" is an English word. An MCP tool is named by its full name, with or without backticks. A short form, such as `archive_session`, does not name it. The same naming rule applies on the refusal-was-right line.

## Risk

Kind of risk: named incident. Landed 2026-11-01.

Incident, 2026-10-31 to 2026-11-01: the classifier refused the coordinator's `mcp__claude-code-remote__archive_session` call, which left about 40 idle sessions. It also refused `add_repo` and the marking of a PR ready. The session noted each refusal only in its handoff. The owner never heard of them.

## Cost

Rule outcomes-mechanize-rules (turn each rule into a check, and state what the check costs) asks this record to state the cost.

- One process start per auto-mode refusal (the hook).
- One file per session that had a refusal. It is gone after the reply names every tool in it.
- Each Stop, inside the report guard that already runs, checks for the session's file, one stat. A session with no refusal reads no file and starts no process.
- A Stop that finds a row with a `tool_use_id` and no `agent_id` also reads the main transcript and the files in `<session>/subagents/`, once. The cost is unmeasured. A session with no refusal reads none of them.
- No timer, no log and no long-lived process.

Proof: `hooks/test_refusal_note.py` case `test_cost_one_refusal_creates_exactly_one_file` proves one file per refusal. `lint/test_report_guard.py` case `PendingRefusalTests.test_g_no_refusals_file_is_a_no_op` proves a Stop with no refusals file writes no file. No test counts the stat, so the one stat per Stop is unmeasured.

Kind: process
Home: hooks/refusal_note.py
