# Hook inputs carry no token counts; the transcript carries total context only

## The question

Step 1 of c151 (the plan step "compaction timing reads message tokens, not total context") asks: can a hook read a "messages only" token count, or only the total context? This record measures. It builds nothing.

## What was run

- Claude Code 2.1.312, container, 2026-10-28. Settings file and config dir in a scratch folder. The repo's settings and `~/.claude` were not touched.
- Hooks were `cat > <scratch>/<event>-$$.json` for `Stop`, `PreCompact` and `statusLine`.
- `claude -p "say hi" --settings <file>` fired `Stop`. A later `claude -p "say bye" --continue` fired `Stop` again.
- `claude -p "/compact" --continue --settings <file>` fired `PreCompact` (manual trigger).
- `statusLine` did not fire in `-p` mode: no capture file was written. Its input is unknown: not run in an interactive session.
- Auto trigger of `PreCompact`: unknown, not run. Its `trigger` value is untested.

## Fields per hook

None of the captured inputs holds a token count, a context size, or a percentage.

- `PreCompact`: `session_id`, `transcript_path`, `cwd`, `scratchpad_dir`, `prompt_id`, `hook_event_name`, `trigger` ("manual"), `custom_instructions` (null). Path fields: `transcript_path`. Token fields: none.
- `Stop`: `session_id`, `transcript_path`, `cwd`, `scratchpad_dir`, `prompt_id`, `permission_mode`, `effort` (object, `level`), `hook_event_name`, `stop_hook_active`, `last_assistant_message`, `background_tasks`, `session_crons`. Token fields: none. Only `transcript_path` leads to counts.
- `statusLine`: unknown. No `context_window` or `used_percentage` field was seen, because none was captured.

## The transcript

Method: read the transcript JSONL. Take each `assistant` entry's `message.usage`. Sum `input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` and `output_tokens`. The counter is a throwaway script, not kept.

- Turn 1 ("say hi"): 2 + 26629 + 10534 + 14 = 37179.
- Turn 2 ("say bye", after `/compact`): 2 + 28525 + 9669 + 17 = 38213.
- The `usage` keys: `input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `output_tokens`, `cache_creation`, `iterations`, `output_tokens_details`, `server_tool_use`, `service_tier`, `inference_geo`, `speed`, `fallback_credit`. None splits system prompt, tool schemas and messages.
- A two-word prompt already shows 37179 input tokens. So the fixed overhead (system prompt, tools, memory files) is about 37k in this run. It dominates a short session. This overhead was loaded from the container's own settings, so it will differ on the owner's machine.
- The `compact_boundary` entry in the transcript holds `preTokens` 37179, `postTokens` 6250, `cumulativeDroppedTokens` 30929. `preTokens` equals the turn 1 usage sum, so it is total context. What `postTokens` counts is unknown. It is below the overhead, so it may leave out the system prompt and tools.
- The `cost-state` entry holds `modelUsage` with per-model totals over the session. Not per message.

## Answer

- No hook input holds a token count. A hook must open `transcript_path`.
- A "messages only" number is not readable from the transcript. Usage sums the whole request.
- A messages-only number can be derived. Proxy: last assistant usage sum minus the first assistant usage sum, since the first turn is mostly overhead. This is untested against a long session. It also breaks when the first turn is large or the overhead changes mid-session (a tool set change, a memory file edit). Mark it a proxy.

## Unknown

- The `statusLine` input fields, and whether it carries context data.
- `PreCompact` with `trigger` auto.
- What `postTokens` counts.
- Whether a long session (many tool calls, subagents) keeps the same `usage` shape.
- Whether the first-turn proxy holds on the owner's machine.

## What step 2 can build on

- A guard hook that already runs may read the last `assistant` usage from `transcript_path` on demand. It starts no process and writes no file (rule `outcomes-mechanize-rules`).
- Total context is exact: the usage sum. Message tokens are a proxy only. Step 2 should say which one it uses.
- First measure `statusLine` in an interactive session, since it may hand over context size with no transcript read.

Raw captures: the scratch folder `c151` under the session scratchpad. Not tracked.

Kind: process
Home: hooks/precompact_handoff_prompt.md
