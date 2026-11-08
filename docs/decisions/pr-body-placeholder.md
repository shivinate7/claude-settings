# A pull request body is never replaced by a placeholder

## The ruling

Incident, 2026-11-08: a cloud lane sent "PLACEHOLDER" as the whole body of PR #1969 (the pull request whose body was lost) through `mcp__github__update_pull_request`. The lost body held review records and Merge-after lines that the lane lint reads. The guard judges each update that sets a body, in two rules.

- Rule `pr-body-placeholder` refuses an update whose stripped body is empty, or one word with no whitespace and at most 40 characters. It reads nothing live.
- Rule `pr-body-shrink` asks when the live body is at least 400 characters and the new body is under one third of it. It reads the live body once, with the merge tool's reader (`merge_module()`, then `Host.pr`). A read that fails passes, and logs one `subject-unread` line.
- The acts are the MCP tool `mcp__github__update_pull_request` with a `body` key, and `gh pr edit` with `--body`, `-b`, `--body-file` or a heredoc body. A title-, state- or draft-only update reads nothing. `gh pr create` and `mcp__github__create_pull_request` are not judged: a first body is no loss.
- `settings.json` adds only `mcp__github__update_pull_request` to the guard's PreToolUse matcher. The create and merge MCP tools stay off it: adding them switches on other refusals (a separate finding).

Why these numbers: sample of 100 recent PRs of this repo, body length min 212, p10 694, median 1243 (read 2026-11-08). A live body under 400 is short, so a short rewrite of it loses little. A new body under one third of the live one is far below a real full rewrite. It asks, never refuses, because a real short rewrite is possible.

Cost: one GitHub read per body update that is not a placeholder, bounded by the merge tool's shared read deadline (a read that times out passes as unread). These rules write no file, and keep no process. A placeholder, a title-, state- or draft-only update costs no read.

Matcher switch-on: adding `mcp__github__update_pull_request` to the guard's PreToolUse matcher also puts that call under the guard's other all-tool steps. Rule `handoff-unread` now judges it after compaction. `session_home_keep` may write the session's lane record (one small file, as for any judged call) on the first judged MCP call of a lane. Neither is a cost of these two rules' own reads.

Limits:

- `gh api -X PATCH .../pulls/N -f body=` is not judged.
- A `gh pr edit` body with a `$` or a backtick is judged when the shell sends it as it stands: a message file, a quoted heredoc (`<<'EOF'`, also inside `$(cat <<'EOF' ...)`) or a single-quoted value. A real expansion (`"$(cat f)"`, an unquoted heredoc holding `$`, text mixed with a variable) is not the text the call sends, so it passes unjudged. A piped body passes unjudged too, even a quoted heredoc piped through `cat` into `--body-file -`, because that heredoc belongs to `cat`.
- A body that is one bare variable (`"$BODY"`, `$BODY`, `"${BODY}"`) is read from the guard's environment. An unset variable reads as empty, because shell state does not carry over between Bash calls. An empty value is refused. The guard does not run the command, so `BODY=$(cat missing.md)` and `BODY=x | gh pr edit ...` still pass. A set value is judged for the placeholder test only, with no live read, so it never asks for a shrink. A variable the same command may assign earlier (`BODY=...;`, `BODY=$(...) &&`, `export BODY=...`, `read BODY`) is unknown and passes unjudged; the test leans to unknown, so `echo BODY=x` before the call also passes. A prefix `BODY=x gh pr edit ... "$BODY"` is no assignment, because bash expands the word before the prefix applies.
- A PowerShell variable (`$body`) is a session variable, not an environment one, and a fresh PowerShell call holds no session variable (lane ruling 2026-11-08 12:00 CST, process-only). The guard never looks the name up in its environment. The name is case-blind. An earlier assignment in the command makes the body unknown, and it passes unjudged:
  - `$body =`, with a scope (`$script:body =`, also `global:`, `local:`, `private:`) or in braces (`${body} =`);
  - `Set-Variable` or `New-Variable` that names it;
  - `foreach ($body`, `[ref]$body`, `-Variable body` or `-OutVariable body`;
  - a dot-source at command position (`. .\vars.ps1`).

  With none of these, the body reads as empty and is refused. `$env:BODY` is out of scope and passes unjudged.
- A variable the shell or a script block sets is unknown, never empty, and passes unjudged: `$_`, `$0`-`$9`, `$@`, `$*` and `$#` in each shell, and PowerShell's automatic variables, such as `$PSItem`, `$args`, `$input`, `$this` and `$Matches`. `$null` stays judged as empty.
- A PowerShell body word that opens with `(`, `$(` or `@(` is an expression, such as `--body (Get-Content body.md -Raw)`. It passes unjudged. A quoted `"(WIP)"` is text and stays judged.
- A `gh pr edit` inside `sh -c` or a command substitution is not read, as cite-by-id does not read it.
- Unmeasured: how often a lane rewrites a body far shorter on purpose.

Kind: process
Home: hooks/guard.py
