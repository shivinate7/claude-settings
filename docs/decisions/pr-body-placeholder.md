# A pull request body is never replaced by a placeholder

## The ruling

Incident, 2026-11-08: a cloud lane sent "PLACEHOLDER" as the whole body of PR #1969 (the pull request whose body was lost) through `mcp__github__update_pull_request`. The lost body held review records and Merge-after lines that the lane lint reads. The guard judges each update that sets a body, in two rules.

- Rule `pr-body-placeholder` denies an update whose stripped body is empty, or one word with no whitespace and at most 40 characters. It reads nothing live.
- Rule `pr-body-shrink` asks when the live body is at least 400 characters and the new body is under one third of it. It reads the live body once, with the merge tool's reader (`merge_module()`, then `Host.pr`). A read that fails passes, and logs one `subject-unread` line.
- The acts are the MCP tool `mcp__github__update_pull_request` with a `body` key, and `gh pr edit` with `--body`, `-b`, `--body-file` or a heredoc body. A title-, state- or draft-only update reads nothing. `gh pr create` and `mcp__github__create_pull_request` are not judged: a first body is no loss.
- `settings.json` adds only `mcp__github__update_pull_request` to the guard's PreToolUse matcher. The create and merge MCP tools stay off it: adding them switches on other refusals (a separate finding).

Why these numbers: sample of 100 recent PRs of this repo, body length min 212, p10 694, median 1243 (read 2026-11-08). A live body under 400 is short, so a short rewrite of it loses little. A new body under one third of the live one is far below a real full rewrite. It asks, never denies, because a real short rewrite is possible.

Cost: one GitHub read per body update that is not a placeholder, no file written, no process kept. A placeholder, a title-, state- or draft-only update costs no read.

Limits:

- `gh api -X PATCH .../pulls/N -f body=` is not judged.
- A `gh pr edit` body that holds a shell expansion (`$` or a backtick), or is piped in with no heredoc, is not the text the guard can read, so it passes unjudged.
- A `gh pr edit` inside `sh -c` or a command substitution is not read, as cite-by-id does not read it.
- Unmeasured: how often a lane rewrites a body far shorter on purpose.

Kind: process
Home: hooks/guard.py
