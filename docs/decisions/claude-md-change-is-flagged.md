# A CLAUDE.md change is flagged

## The ruling

Owner, 2026-10-16: report only, no hold. A green PR that changes a rule file merges under the standing grant.

- After the merge, `bin/merge` prints one line per changed file: `merge: #<n> changes <path>, a rule file every session loads.`
- The files are `CLAUDE.md`, `.claude/CLAUDE.md` and each file under `output-styles/`. The match ignores case, because Windows loads `claude.md` as `CLAUDE.md`. The line prints the path as git names it, escaped if the console cannot print it. A rename flags the old path and the new path.
- The paths come from `git diff --name-only --no-renames -z <base>...<sha>`. If that read fails, the tool prints that the rule-file check could not run, and the merge goes on.
- The session's report names each such file in bold, in the Done line of that merge.
- Agents, skills and `settings.json` are not flagged.

Why: the clone's `CLAUDE.md` is the install source. It reaches main only by a PR, and under the standing grant nothing told the owner a merged PR changed it.

Kind: build
Plan: docs/decisions/claude-md-change-is-flagged.md#the-ruling (all)
