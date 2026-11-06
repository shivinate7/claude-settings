# Cloud start hooks run the code install.sh just copied

## The ruling

In a cloud session, `install.sh --cloud` runs the repo's startup hooks itself, after it has copied them into `~/.claude`.
The `~/.claude/settings.json` it writes holds no SessionStart entry that fires on `startup`, except its own refresh hook.
An entry fires on a source when its matcher is `""`, `*` or missing, or when the matcher, as an anchored regex, matches the source.

- The refresh hook passes the hook input to `install.sh` in `CS_HOOK_INPUT`. `install.sh` reads `.source` from it, and with no readable input it takes `startup`.
- A dropped entry runs only when it fires on that source, in the order of the repo `settings.json`. Its output is part of the refresh hook's output.
- Its stdin is the text of `CS_HOOK_INPUT`, or empty when that is unset, as Claude Code gives a hook its input. It is never `install.sh` itself, which `bash -s` reads from stdin.
- Each entry is bounded by its own `timeout` field, default 10 seconds, with `timeout`. A cut entry is logged as a WARNING, and the next entry runs. Without `timeout` on the machine (macOS), a shell watchdog bounds the entry the same way: it runs the entry in its own process group and kills the group at the bound, so a grandchild does not outlive the cut.
- Each run has `CLAUDE_CODE_REMOTE=true`: the install is in the cloud by definition. The repo's pull hook keeps its own cloud exit, and `actions/ste-lint/test_action.py` starts no background fetch.
- A failing entry is logged and never fails the install. Matchers are anchored, so `startup` does not fire on `resume`, and `startup_x` does not fire on `startup`. If `install.sh` cannot read the entries, it logs a WARNING and runs none.
- Without `jq`, `settings.json` is copied whole, nothing is dropped, and nothing runs here.
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

- The fix lands in a container only once its snapshot holds the new `settings.json`. An older snapshot still runs its stale startup hooks, and then `install.sh` runs the fresh ones too.
  A stale line can show beside the fresh one until the environment's snapshot is rebuilt.
  So on a startup run, `install.sh` warns once when the old `settings.json` still holds a startup entry other than the refresh hook (old or new form), and names the fix: edit the environment and save its Setup script.
  It reads only local state. A run with no hook input (a snapshot from before the refresh hook passed it) counts as a hook run only when `CLAUDE_PROJECT_DIR` is set, so the snapshot build stays silent. A resume run is silent.
  Cost: one `jq` run on the old file, only on a cloud startup run with that file present; no network call, no new file.
  Ruled by: the claude-settings coordinator, lane cloud-snapshot-age-check, 2026-11-06 14:42 CST (warn on the harm, a stale startup entry, never on hooks/ lag alone).
- The setup script (`cloud-setup.sh`) runs `install.sh --cloud` with no hook input, so the startup entries also run once at snapshot build. `daily_note.py` then stamps that Central day, and a session on the same day skips its guard.log note. Note: cloud-setup-runs-start-hooks.
- An entry that fires on resume but not on startup (matcher `resume`) is neither dropped nor run, so it still runs stale. The repo has none. Note: cloud-resume-only-hook-stale.
- Cost: no new process type. The startup hooks start once per session start, as before, from inside the refresh hook (unmeasured).

Kind: build
Plan: docs/decisions/cloud-start-hooks-run-fresh.md#the-ruling (linux)
Home: install.sh
