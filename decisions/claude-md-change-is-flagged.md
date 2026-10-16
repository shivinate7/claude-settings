# A CLAUDE.md change is flagged

## The question

How does the owner know when a merged PR changed the rules that every session loads, without
holding every such merge for the owner's word?

## The ruling

Owner, 2026-10-16 03:27 CDT: "Report only." (Feedback item fb-claude-md-flag: "how can i
confirm an agent does not just edit claude.md without asking me first".)

- No hold. A green PR that changes these files merges under the standing grant, as now.
- After the merge, `bin/merge` prints one line per changed file:
  `merge: #<n> changes <path>, a rule file every session loads.`
- The files are `CLAUDE.md`, `.claude/CLAUDE.md` and each file under `output-styles/`. The
  match ignores case, because Windows loads `claude.md` as `CLAUDE.md`. The line prints the
  path as git names it. A name the console cannot print shows escaped, such as `名`.
  A rename flags the old path and the new path.
- The paths come from `git diff --name-only --no-renames -z <base>...<sha>`, the PR's own
  changes. If that read fails, the tool prints that the rule-file check could not run, and
  the merge goes on. A read that cannot run is unknown, never clear.
- The session's report names each such file in bold, in the Done line of that merge.
- Owner, 2026-10-16 04:30 CDT: "Keep as is." Agents, skills and `settings.json` are not
  flagged.

## Why

The installed `~/.claude/CLAUDE.md` is frozen: the guard refuses a write to it
(hooks/guard_frozen.py). The clone's copy is the install source, so it stays editable. It
reaches main only by a PR. Under the standing merge grant, nothing told the owner that a
merged PR changed it.

## Holes, named

- The owner learns of a flag only when the session's report names it in bold. No check
  enforces that step. A crash between the merge and the print, such as a broken pipe, loses
  the flag, as it loses the "merged as" line. Debt `rule-flag-not-enforced` (the bold flag is
  not enforced).
- Only `bin/merge` prints the flag. A merge made with `gh pr merge` or the web page is not
  flagged. Same debt.

Kind: build
Plan: decisions/claude-md-change-is-flagged.md#the-ruling (all)
