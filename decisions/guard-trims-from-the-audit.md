# Guard trims from the audit

## The ruling

The owner approved these trims from an audit of `~/.claude/guard.log`. `building-guard-needs-incident` says a guard rule needs a named incident or a measured risk. A rule that never fires, or only logs, has neither. 0 fires in the log is a lower bound, not proof of no risk.

- Cut `merge-main` (noted allow). It only logged, and the config report already names each merge from the transcript. The cut also removes a `gh pr view` network call before every `gh pr merge`. `hooks/guard.py` loses `merge_base`, `GH_PR_MERGE`, `MERGE_TOOLS` and rule 6. The merge MCP tool leaves the PreToolUse matcher in `settings.json`.
- Fold `conflict-resolve` (noted allow) into `shared-tree`. A `git checkout --ours`, `--theirs` or `--merge` in a tree with an unresolved conflict still passes, with no rule name or log line of its own.
- Keep `frozen-path`, with no new watch. `hooks/config_watch.py` `WATCHED_NAMES` is the project's `.claude/settings.json` and `.claude/settings.local.json`. It reverts only a change to the subagent model cap. The settings deny list covers the Edit tool but not a Bash write. So a `cp`, `mv` or redirect onto `~/.claude/hooks/guard.py` has no other check.
- Keep `destructive-delete`, `subagent-model-floor` and `machine-wide-kill`. Bypass mode shows no prompt.
- `env-file` no longer judges `Read` and `Grep`. The settings deny list blocks `Read(.env)`, `Read(.env.*)`, `Read(**/.env)` and `Read(**/.env.*)`, with `Read(!**/.env.example)`. `Write`, `Edit`, `MultiEdit` and `NotebookEdit` stay denied. How the patterns match is per Claude Code permission rules, unmeasured here. The regex-as-path fix is in `env-file-wrappers`.
- `guard.py` leaves at once for `Read` and `Grep`, and the PreToolUse matcher in `settings.json` drops them. Effect: a subagent's first call writes no home record when it is a `Read` or `Grep`. The next write or shell call writes it from the same worktree.
- `janitor/agent_end_reap.py` keeps `state/agent-end-payloads.jsonl`, capped at the last 200 lines. The cap writes a temp file and renames it over the log, so a reader never sees an empty file. `agent-end-reap-stops-what-a-finished-agent-left` names the file as evidence for payload fields the docs leave open, and `janitor/prove_agent_end_reap.py` reads its last line.
- Subagent model cap, settings writes: the guard's shell ask stays, with its five cases and two mutants. `config_watch` stays the second layer. It reverts every shell cap change that the guard did not ask about, in every shape. Why: the watch reads only the watched paths of the current directory, so a write from a subdirectory or another worktree escaped it alone.
- `hooks/config_report.py` is a section of `hooks/decision_watch.py`, and its Stop entry is gone from `settings.json`. One process runs for both at each Stop. It reads the transcript through `lint/_transcript.py` (`hooks-share-the-transcript-reader`).

Limit: `lint/rule_mechanisms.json` and its `unmechanized` pin do not change, because no row names a cut rule. `config_watch` enforces the expiry.

Kind: process
Home: hooks/guard.py
