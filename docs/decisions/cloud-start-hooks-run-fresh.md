# Cloud start hooks run the code install.sh just copied

## The ruling

In a cloud session, `install.sh --cloud` runs the repo's startup hooks itself, after it has copied them into `~/.claude`.
The `~/.claude/settings.json` it writes holds no SessionStart entry that matches `startup`, except its own refresh hook.

- The refresh hook passes the hook input to `install.sh` in `CS_HOOK_INPUT`. `install.sh` reads `.source` from it, and with no readable input it takes `startup`.
- A dropped entry runs only when its matcher matches that source, in the order of the repo `settings.json`, with stdin from `/dev/null`. Its output is part of the refresh hook's output.
- Each run has `CLAUDE_CODE_REMOTE=true`: the install is in the cloud by definition. The repo's pull hook keeps its own cloud exit, and `actions/ste-lint/test_action.py` starts no background fetch.
- A failing entry is logged and never fails the install. Matchers are anchored, so `startup` does not match `resume`. Without `jq`, `settings.json` is copied whole, nothing is dropped, and nothing runs here.
- Entries for other sources (`compact`, `clear|fork`) stay in `settings.json`: they fire after the refresh.
- Local installs are unchanged. Their `settings.json` links to the clone, so the hooks are never stale.

Ruled by: the claude-settings coordinator, lane cc-facts-unknown-cloud, 2026-11-03 (coordinator brief: fix the cause, never mute a real unknown).

## The defect it stops

A cloud container starts from an environment snapshot, made by the setup script at an earlier main.
At SessionStart, Claude Code runs the matching hooks in parallel.
So `hooks/daily_note.py` ran the snapshot's stale `hooks/precompact_handoff.py` before the refresh hook replaced it.

- Seen 2026-11-03: a snapshot made 21:34 UTC predates commit d40b779 (the PATH fallback for the Claude Code binary, 22:02 UTC).
  Each new lane session printed "compaction facts are unknown: CLAUDE_CODE_EXECPATH is not set", in the pre-fix wording, and named it under Input Needed. Four or more lanes did so.
- Timing in one container: `cc-behavior.json` written 04:01:18.6 UTC, `~/.claude/hooks` refreshed 04:01:23.9 UTC.
- Main's check, given the same env (AI_AGENT set, PATH with `/opt/node22/bin`, no CLAUDE_CODE_EXECPATH), reads `/opt/claude-code/bin/claude` and prints nothing. The PATH inside the hook env itself is unmeasured; the claude process's PATH holds `/opt/node22/bin`.

## Limits

- The fix lands in a container only once its snapshot holds the new `settings.json`. An older snapshot still runs its stale startup hooks, and then `install.sh` runs the fresh ones too, so a stale line can show beside the fresh one until the environment's snapshot is rebuilt.
- Cost: no new process type. The startup hooks start once per session start, as before, from inside the refresh hook.

Kind: build
Plan: docs/decisions/cloud-start-hooks-run-fresh.md#the-ruling (linux)
Home: install.sh
