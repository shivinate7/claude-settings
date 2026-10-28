# PreCompact and Stop inputs carry no token counts; statusLine and the transcript carry total context only

## The question

c151 is the plan item "compaction timing reads message tokens, not total context". Its step 1 is this measurement. Its step 2 is the build that would use the result. Step 1 asks: can a hook read a "messages only" token count, or only the total context? This record measures. It builds nothing.

## What was run

- Claude Code 2.1.312, container, 2026-10-28. Settings file and config dir in a scratch folder. The repo's settings and `~/.claude` were not touched.
- Hooks were `cat > <scratch>/<event>-$$.json` for `Stop`, `PreCompact` and `statusLine`.
- `claude -p "say hi" --settings <file>` fired `Stop`. A later `claude -p "say bye" --continue` fired `Stop` again.
- `claude -p "/compact" --continue --settings <file>` fired `PreCompact` (manual trigger).
- `statusLine` did not fire in `-p` mode: no capture file was written.
- `statusLine` fired in an interactive session: `tmux new-session -d` running `claude --settings <file>`, the trust prompt answered Yes, then `say hi`. The hook was `cat > <scratch>/statusline-$$.json`.
- `PreCompact` with trigger auto: an interactive run started with `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=3`, then `say hi` and `say bye`. The auto `PreCompact` hook fired (`PreCompact-1044.json`). The work3 transcript holds no `compact_boundary` entry, so whether the compaction completed is unknown.

## Fields per hook

`PreCompact` and `Stop` inputs hold no token count, context size or percentage. `statusLine` does.

- `PreCompact`: `session_id`, `transcript_path`, `cwd`, `scratchpad_dir`, `prompt_id`, `hook_event_name`, `trigger` ("manual"), `custom_instructions` (null). Path fields: `transcript_path`, `cwd`, `scratchpad_dir`. Token fields: none.
- `Stop`: `session_id`, `transcript_path`, `cwd`, `scratchpad_dir`, `prompt_id`, `permission_mode`, `effort` (object, `level`), `hook_event_name`, `stop_hook_active`, `last_assistant_message`, `background_tasks`, `session_crons`. Path fields: `transcript_path`, `cwd`, `scratchpad_dir`. Token fields: none. Only `transcript_path` leads to counts.
- `PreCompact` with trigger auto: the same keys as manual, with `trigger` "auto". No token fields.
- `statusLine` (interactive): `session_id`, `transcript_path`, `cwd`, `scratchpad_dir`, `prompt_id`, `effort.level`, `model.id`, `model.display_name`, `workspace.current_dir`, `workspace.project_dir`, `workspace.added_dirs`, `version`, `output_style.name`, `cost.*` (dollars, durations, lines), `exceeds_200k_tokens`, `fast_mode`, `thinking.enabled`, and `prompt_cache.*`. Path fields: `transcript_path`, `cwd`, `scratchpad_dir`, `workspace.*`.
- `statusLine` `prompt_cache` keys (from `statusline-1048.json`): `warm`, `caching_observed`, `ttl`, `expires_at`, `requests`, `misses`, `expected_rebuilds`, `hit_ratio`, `cache_write_tokens`, `miss_recache_tokens`, `last_miss_at`, `last_miss_cause`, `miss_causes`, `recache_tokens_if_cold`. Those with token counts: `cache_write_tokens`, `miss_recache_tokens`, `recache_tokens_if_cold`.
- `statusLine` token fields: `context_window.total_input_tokens`, `context_window.total_output_tokens`, `context_window.context_window_size` (1000000), `context_window.current_usage.{input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens}`, `context_window.used_percentage`, `context_window.remaining_percentage`.
- Before the first reply, the first `statusLine` call (`statusline-894.json`, `statusline-1014.json`) held `current_usage`, `used_percentage` and `remaining_percentage` as null and the token totals as 0. Those two captures have no `prompt_id` key and no `prompt_cache` key.

## The transcript

Method: read the transcript JSONL. Take each `assistant` entry's `message.usage`. Sum `input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` and `output_tokens`. The counter is a throwaway script, not kept.

- Turn 1 ("say hi"): 2 + 26629 + 10534 + 14 = 37179.
- Turn 2 ("say bye", after `/compact`): 2 + 28525 + 9669 + 17 = 38213.
- Run 2 (interactive, Sonnet 5.5, work2): turn 1 sum 42132. Run 3 (interactive, work3, auto test): turn 1 sum 36632, turn 2 sum 36674.
- The `usage` keys: `input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `output_tokens`, `cache_creation`, `iterations`, `output_tokens_details`, `server_tool_use`, `service_tier`, `inference_geo`, `speed`, `fallback_credit`. None of these keys splits system prompt, tool schemas and messages.
- A two-word prompt already shows 36.6k to 42.1k input tokens: 37179 (first run, Opus), 36632 (work3, Opus), 42132 (work2, Sonnet 5.5). So the fixed overhead (system prompt, tools, memory files) is 36.6k to 42.1k here. It varies by model and run, and it dominates a short session. It was loaded from the container's own settings, so it will differ on the owner's machine. The `statusLine` comparison below uses 42132 because that is the run whose `statusLine` and transcript were read together first.
- The `compact_boundary` entry (the transcript line that marks a finished compaction) holds `preTokens` 37179, `postTokens` 6250, `cumulativeDroppedTokens` 30929. `preTokens` equals the turn 1 usage sum, so it is total context. What `postTokens` counts is unknown. It is below the overhead, so it may leave out the system prompt and tools.
- The `cost-state` entry (a transcript line with session cost totals) holds `modelUsage` with per-model totals over the session. Not per message.

## statusLine against the transcript

- After `say hi`: `current_usage` was 2 + 0 + 42117 (input, read, creation) and output 13. The transcript usage was the same four numbers, sum 42132.
- `total_input_tokens` 42119 is `input_tokens` + cache read + cache creation. It leaves out output. `used_percentage` was 4. 42119 over 1000000 is 4.2%, and 36661 over 1000000 is 3.67%. Both show 4, so the rounding rule is unknown.
- A second run read 36661 = 2 + 31930 + 4729, the same way.
- So `statusLine` `current_usage` equals the transcript's last usage in both runs, with no transcript read. None of the `statusLine` keys seen splits system, tools and messages.
- `statusLine` fired in the interactive session. In `-p` mode no capture file appeared. How often it fires, and whether any other hook can read its fields, is unknown.

## Answer

- `PreCompact` and `Stop` inputs hold no token count. Those hooks must open `transcript_path`. Only `statusLine` holds counts, and it was seen only in an interactive session.
- A "messages only" number is not readable from the transcript. Usage sums the whole request.
- A messages-only number can be derived. Proxy: last assistant usage sum minus the first assistant usage sum, since the first turn is mostly overhead. This is untested against a long session. It also breaks when the first turn is large or the overhead changes mid-session (a tool set change, a memory file edit). Mark it a proxy.

## Unknown

- Why `statusLine` wrote no file in `-p` mode: not fired, or not run. Only the absence was seen.
- How `used_percentage` rounds.
- Whether the auto compaction completed in the work3 run.
- How often `statusLine` fires.
- `statusLine` in a session with agents or after a compact: its `current_usage` there was not read.
- Whether `statusLine` or the transcript counts the system prompt and tools the same way `preTokens` does after a compact.
- What `postTokens` counts.
- Whether a long session (many tool calls, agents) keeps the same `usage` shape.
- Whether the first-turn proxy holds on the owner's machine.

## What step 2 can build on

- A guard hook that already runs may read the last `assistant` usage from `transcript_path` on demand. It starts no process and writes no file (rule `outcomes-mechanize-rules`, the CLAUDE.md rule that tracking reads on demand inside a process already running).
- Total context is exact: the usage sum. Message tokens are a proxy only. Step 2 should say which one it uses.
- `statusLine` gave total context with no transcript read in interactive runs. The transcript gave the same numbers in every run made. Whether a guard hook can get the `statusLine` fields is unknown.

Raw captures: the scratch folder `c151` under the session scratchpad. Not tracked.

Kind: process
Home: hooks/precompact_handoff_prompt.md
