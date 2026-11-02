# A refused tool call reaches the owner

## The ruling

Owner-side goal: when the auto-mode classifier refuses a tool call, the owner hears of it in the session's reply. A session may not keep a refusal only in its handoff.

- `hooks/refusal_note.py` runs on the PermissionDenied event. It adds one line, `{ts, tool_name, reason}`, to `<config dir>/state/refusals/<session_id>.jsonl`.
- A reason that starts with "Auto mode could not evaluate this action" or "Classifier unavailable" is a classifier outage with no verdict. The hook writes nothing for it. "Starts with" is literal: a reason that only holds the phrase is a real refusal.
- A tool that is already pending in the file is not added again. The hook skips a line that is not JSON when it reads the file, so a bad line never stops a new refusal being recorded.
- The hook prints nothing, never prints `retry`, and exits 0 on every path. The event reads only `retry`, and ignores the exit code and stderr (https://code.claude.com/docs/en/hooks#permissiondenied).
- `lint/report_guard.py` reads the file at every Stop, landed or not. A pending tool that the reply does not name in its Input Needed section blocks the Stop. The reason quotes the tool's full name in backticks, so one rewrite that names it clears it. It asks for an Input Needed line "allow `<tool_name>`?" and a line in `docs/debts/notes.md`.
- Each tool that the reply names under Input Needed leaves the file. The rest stay pending. The file goes when none is left.
- A Stop with `stop_hook_active` set never blocks on a refusal. It still clears each tool its reply names.
- A name outside Input Needed is no answer.
- A built-in tool such as `Edit` or `Bash` is named only in backticks, because a bare "Edit" is an English word. An MCP tool is named by its full name, with or without backticks. A short form, such as `archive_session`, does not name it.

## Risk

Kind of risk: named incident. Landed 2026-11-01.

Incident, 2026-10-31 to 2026-11-01: the classifier refused the coordinator's `mcp__claude-code-remote__archive_session` call, which left about 40 idle sessions. It also refused `add_repo` and the marking of a PR ready. The session noted each refusal only in its handoff. The owner never heard of them.

## Cost

Rule outcomes-mechanize-rules (turn each rule into a check, and state what the check costs) asks this record to state the cost.

- One process start per auto-mode refusal (the hook).
- One file per session that had a refusal. It is gone after the reply names every tool in it.
- Each Stop, inside the report guard that already runs, checks for the session's file, one stat. A session with no refusal reads no file and starts no process.
- No timer, no log and no long-lived process.

Proof: `hooks/test_refusal_note.py` case `test_cost_one_refusal_creates_exactly_one_file` proves one file per refusal. `lint/test_report_guard.py` case `PendingRefusalTests.test_g_no_refusals_file_is_a_no_op` proves a Stop with no refusals file writes no file. No test counts the stat, so the one stat per Stop is unmeasured.

Kind: process
Home: hooks/refusal_note.py
