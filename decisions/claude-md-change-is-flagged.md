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
- The files are `CLAUDE.md`, `.claude/CLAUDE.md` and each file under `output-styles/`.
- The session's report names each such file in bold, in the Done line of that merge.

## Why

The installed `~/.claude/CLAUDE.md` is frozen: the guard refuses a write to it
(hooks/guard_frozen.py). The clone's copy is the install source, so it stays editable. It
reaches main only by a PR. Under the standing merge grant, nothing told the owner that a
merged PR changed it.

Kind: build
Plan: decisions/claude-md-change-is-flagged.md#the-ruling (all)
