# Hook inputs carry no token counts; the transcript carries total context only

## The question

Step 1 of c151 (the plan step "compaction timing reads message tokens, not total context") asks: can a hook read a "messages only" token count, or only the total context? This record measures. It builds nothing.

## What was run

- Claude Code 2.1.312, container, 2026-10-28. Settings file and config dir in a scratch folder. The repo's settings and `~/.claude` were not touched.
- Hooks were `cat > <scratch>/<event>-$$.json` for `Stop`, `PreCompact` and `statusLine`.
- `claude -p "say hi" --settings <file>` fired `Stop`. A later `claude -p "say bye" --continue` fired `Stop` again.
- `claude -p "/compact" --continue --settings <file>` fired `PreCompact` (manual trigger).
- `statusLine` did not fire in `-p` mode: no capture file was written.
- `statusLine` fired in an interactive session: `tmux new-session -d` running `claude --settings <file>`, the trust prompt answered Yes, then `say hi`. The hook was `cat > <scratch>/statusline-$$.json`.
- `PreCompact` with trigger auto: the same interactive run with `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=3`. The 36k baseline passed 3% of a 1M window, so a second prompt compacted.

## Fields per hook

`PreCompact` and `Stop` inputs hold no token count, context size or percentage. `statusLine` does.

- `PreCompact`: `session_id`, `transcript_path`, `cwd`, `scratchpad_dir`, `prompt_id`, `hook_event_name`, `trigger` ("manual"), `custom_instructions` (null). Path fields: `transcript_path`. Token fields: none.
- `Stop`: `session_id`, `transcript_path`, `cwd`, `scratchpad_dir`, `prompt_id`, `permission_mode`, `effort` (object, `level`), `hook_event_name`, `stop_hook_active`, `last_assistant_message`, `background_tasks`, `session_crons`. Token fields: none. Only `transcript_path` leads to counts.
- `PreCompact` with trigger auto: the same keys as manual, with `trigger` "auto". No token fields.
- `statusLine` (interactive): `session_id`, `transcript_path`, `cwd`, `scratchpad_dir`, `prompt_id`, `effort.level`, `model.id`, `model.display_name`, `workspace.current_dir`, `workspace.project_dir`, `workspace.added_dirs`, `version`, `output_style.name`, `cost.*` (dollars, durations, lines), `exceeds_200k_tokens`, `fast_mode`, `thinking.enabled`, and `prompt_cache.*` (also token counts: `cache_write_tokens`, `recache_tokens_if_cold`).
- `statusLine` token fields: `context_window.total_input_tokens`, `context_window.total_output_tokens`, `context_window.context_window_size` (1000000), `context_window.current_usage.{input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens}`, `context_window.used_percentage`, `context_window.remaining_percentage`.
- Before the first reply, the first `statusLine` call held `current_usage`, `used_percentage` and `remaining_percentage` as null and the token totals as 0.

## The transcript

Method: read the transcript JSONL. Take each `assistant` entry's `message.usage`. Sum `input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` and `output_tokens`. The counter is a throwaway script, not kept.

- Turn 1 ("say hi"): 2 + 26629 + 10534 + 14 = 37179.
- Turn 2 ("say bye", after `/compact`): 2 + 28525 + 9669 + 17 = 38213.
- The `usage` keys: `input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `output_tokens`, `cache_creation`, `iterations`, `output_tokens_details`, `server_tool_use`, `service_tier`, `inference_geo`, `speed`, `fallback_credit`. None splits system prompt, tool schemas and messages.
- A two-word prompt already shows 37179 input tokens. So the fixed overhead (system prompt, tools, memory files) is about 37k in this run. It dominates a short session. This overhead was loaded from the container's own settings, so it will differ on the owner's machine.
- The `compact_boundary` entry in the transcript holds `preTokens` 37179, `postTokens` 6250, `cumulativeDroppedTokens` 30929. `preTokens` equals the turn 1 usage sum, so it is total context. What `postTokens` counts is unknown. It is below the overhead, so it may leave out the system prompt and tools.
- The `cost-state` entry holds `modelUsage` with per-model totals over the session. Not per message.

## statusLine against the transcript

- After `say hi`: `current_usage` was 2 + 0 + 42117 (input, read, creation) and output 13. The transcript usage was the same four numbers, sum 42132.
- `total_input_tokens` 42119 is `input_tokens` + cache read + cache creation. It leaves out output. `used_percentage` 4 is that figure over 1000000, rounded down.
- A second run read 36661 = 2 + 31930 + 4729, the same way.
- So `statusLine` hands over the transcript's last usage as total context, with no transcript read. It does not split system, tools and messages either.
- `statusLine` is a display hook. It runs per screen refresh in a live session, and it is not run by `claude -p`. A guard hook cannot call it. Its fields are readable only by a command the owner sets as `statusLine`.

## Answer

- `PreCompact` and `Stop` inputs hold no token count. Those hooks must open `transcript_path`. Only `statusLine` holds counts, and only in an interactive session.
- A "messages only" number is not readable from the transcript. Usage sums the whole request.
- A messages-only number can be derived. Proxy: last assistant usage sum minus the first assistant usage sum, since the first turn is mostly overhead. This is untested against a long session. It also breaks when the first turn is large or the overhead changes mid-session (a tool set change, a memory file edit). Mark it a proxy.

## Unknown

- `statusLine` in a session with subagents or after a compact: its `current_usage` there was not read.
- Whether `statusLine` or the transcript counts the system prompt and tools the same way `preTokens` does after a compact.
- What `postTokens` counts.
- Whether a long session (many tool calls, subagents) keeps the same `usage` shape.
- Whether the first-turn proxy holds on the owner's machine.

## What step 2 can build on

- A guard hook that already runs may read the last `assistant` usage from `transcript_path` on demand. It starts no process and writes no file (rule `outcomes-mechanize-rules`).
- Total context is exact: the usage sum. Message tokens are a proxy only. Step 2 should say which one it uses.
- `statusLine` gives total context with no transcript read, but only in an interactive session and only to the command set as `statusLine`. The transcript works in every mode.

Raw captures: the scratch folder `c151` under the session scratchpad. Not tracked.

Kind: process
Home: hooks/precompact_handoff_prompt.md
