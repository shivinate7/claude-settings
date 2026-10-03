# Guard trims from the audit

The owner approved these trims from an audit of `~/.claude/guard.log`: 2,713 lines, 2026-09-16
to 2026-10-02. The log holds refusals and noted allows. CLAUDE.md `building-guard-needs-incident`
says a guard rule needs a named incident or a measured risk. A rule that never fires, or only
logs, has neither. The counts below come from that log, unless marked otherwise.

## Cut

| Rule | Fires | Reason |
|---|---|---|
| `merge-main` (noted allow) | 185 lines | It only logged. The config report already names each merge from the transcript. The cut also removes a `gh pr view` network call, with a 10 second timeout, before every `gh pr merge`. |
| `conflict-resolve` (noted allow) | 7 lines | Folded into `shared-tree`. A `git checkout --ours`, `--theirs` or `--merge` in a tree with an unresolved conflict still passes, as before. It has no rule name or log line of its own. |

`hooks/guard.py` loses `merge_base`, `GH_PR_MERGE`, `MERGE_TOOLS` and rule 6. The merge MCP tool leaves
the PreToolUse matcher in `settings.json`.

## Not cut: `frozen-path`

The audit found 0 fires. The brief said to cut it only if `hooks/config_watch.py` catches a Bash
redirect or `cp` onto the paths the rule freezes. It does not.

- `hooks/config_watch.py` `WATCHED_NAMES` is the project's `.claude/settings.json` and
  `.claude/settings.local.json`, taken from the current directory. Its own comment says the config
  directory is not watched.
- It reverts only a change to the subagent model cap. It does not look at any other content.
- The settings deny list covers the Edit tool on `~/.claude/settings.json`, `CLAUDE.md`, `hooks/**`,
  `lint/**`, `agents/**`, `janitor/**` and `state/**`. It does not cover a Bash write.

So a `cp`, `mv` or redirect onto `~/.claude/hooks/guard.py` has no other check. The rule stays. To
cut it, first add a watch of those paths. The 0 fires show that nothing tried the act. They do not
show that the act is safe.

## Fixed

- `env-file` read a regex as a path. 65 denies matched `'.*'`, the pattern of a `grep`. The guard now
  skips the pattern word of a search command (`grep`, `egrep`, `fgrep`, `rg`, `ag`, `ack`). `-e` and
  `--regexp` mark the pattern. Without them, the first plain word is the pattern, after the values
  of `-A`, `-B`, `-C` and `-m`. A path word is still judged, so `grep foo .*` and `cat .*` still deny.
  With `-f`, `--file` or `--file=`, the patterns come from a file, so nothing is skipped and the
  value is judged as a path: `grep -f .env x` denies.
- `env-file` no longer judges `Read` and `Grep`. The settings deny list blocks `Read(.env)` and
  `Read(.env.*)`. The log holds 0 `env-file` denies for those two tools. `Write`, `Edit`,
  `MultiEdit` and `NotebookEdit` stay denied.
- `guard.py` leaves at once for `Read` and `Grep`. No rule judges them: `worktree-home` skips them,
  and a frozen path stays readable. The early exit also skips the git call that `worktree-home` made
  on each read. One effect: a subagent's first call no longer writes its home record when that call
  is a `Read` or `Grep`. The next write or shell call writes it from the same worktree. The
  PreToolUse matcher in `settings.json` also drops `Read` and `Grep`, so no process starts for them.
  Without the guard, the deny list alone blocks `.env` reads. `settings.json` now also denies
  `Read(**/.env)` and `Read(**/.env.*)`, with `Read(!**/.env.example)`, so a read in a subfolder
  stays blocked. How those patterns match is per Claude Code permission rules. It is unmeasured
  here.
- `janitor/agent_end_reap.py` wrote every raw SubagentStop payload to
  `state/agent-end-payloads.jsonl`: 3,939 lines at the audit. The entry
  `agent-end-reap-stops-what-a-finished-agent-left` names the file as the evidence for payload
  fields that the docs leave open, and `janitor/prove_agent_end_reap.py` reads its last line. So
  the file stays, capped at the last 200 lines. The cap writes a temp file and renames it over the
  log, so a reader never sees an empty file.

## Folded

- Subagent model cap, settings writes: NOT moved. A first draft moved the shell route to
  `hooks/config_watch.py` alone. The reviewer found a hole. The watch reads only the watched paths
  of the current directory. A shell write from a subdirectory or from another worktree was
  neither reverted nor reported. The guard's shell ask is back, with its five cases and two
  mutants. `config_watch` stays the second layer. It reverts every shell cap change that the guard
  did not ask about, in every shape. The guard asks before the write, and the watch reverts after it.
- `hooks/config_report.py` is a section of `hooks/decision_watch.py`, and its Stop entry is gone from
  `settings.json`. The message and the checks are the same. One process now runs for both at each
  Stop. It reads the transcript through `lint/_transcript.py`
  (`hooks-share-the-transcript-reader`).

## Merge with `stop/cheap-turn-end`

That branch (PR 239) edits `hooks/decision_watch.py` (docstring, one import, `incident_key`, `run`),
`hooks/config_report.py` and `lint/_transcript.py` (it adds `read_turn` and `last_human_epoch`).
This change adds one section to `decision_watch.py` and edits `main`, so the two do not share a
hunk there. Two conflicts are certain and small:

1. PR 239 edits `hooks/config_report.py`, and this change deletes it. Delete the file in the
   merge. Then apply the two edits of PR 239 to `config_report` in `decision_watch.py`. Read
   `human, after = read_turn(path)` in place of `read_transcript` and `records_after_last_human`,
   and call `last_human_stamp([human] if human else [])`.
2. Both change the top of `decisions/hooks-share-the-transcript-reader.md`. Keep both texts.

## Not covered

`lint/rule_mechanisms.json` and its pin (70 `unmechanized`) do not change, because no row names a cut
rule. The rows for `roles-override-carries-expiry` and `roles-remove-override-file` still cite guard
rule `subagent-model-cap`, though the expiry is the work of `config_watch`. That was true before this
change.

Not touched, by instruction: `destructive-delete`, `subagent-model-floor` and `machine-wide-kill`.
Bypass mode shows no prompt, so they stay.

Fixed after review: 29 `env-file` denies read "only a runner may be handed '.env' with
--env-file, and 'Semwal' is not one". The cause was a quoted assignment value with a space, as in
`ADMINS='Shivam Semwal' node --env-file=.env server.ts`. The guard split words on spaces, so the tail
of the value read as the command word. `_assignment_end` now spans the quoted value. The owner ruled
that `frozen-path` stays, with no new watch.

Also fixed after review: an unquoted heredoc body with no `$(...)` made `env_heredoc_refusal` raise an
IndexError. The guard failed open, so every rule after the env check was skipped. The body is now
judged and passes. The top-level crash handler of `guard.py` now logs one `crash` line, so the next
hidden crash shows in `guard.log`.
