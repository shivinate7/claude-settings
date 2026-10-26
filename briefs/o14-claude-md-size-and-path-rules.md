# o14: repo CLAUDE.md stays small; folder-only rules load by path

Cloud build thread brief. Build advisor (2), Oct 26, against claude-settings main bf084df.
Base: main bf084df; never rebase onto main after review. claude-settings only: do not touch other repos.

## Why

Every session loads the whole repo CLAUDE.md plus the global one. banchi's is 399 lines, mailaudit's
478. Claude Code's memory docs aim under 200 lines and offer path-scoped rules (.claude/rules/*.md with
a `paths:` glob) that load only when Claude touches matching files (code.claude.com/docs/en/memory;
verify the current front-matter shape there before you build). Repo pilots are o3's, deferred.

## Task, one lane

1. Size check: a lint that warns (never fails) when a CLAUDE.md passes 200 lines. Give it one home
   that child repos can call later (compliance-check or a lint/ script); in this repo, run it in CI on
   CLAUDE.md and .claude/CLAUDE.md. A warning names the line count and the doc link.
2. Rule: one short CLAUDE.md sentence (STE, under 30 words) on when a section moves to a path-scoped
   rule: it matters only under one folder. It stays when it is needed before the first file read
   (a design pass, a merge rule). Add its rule anchor and its rule_mechanisms.json row.
3. Read-deny guidance: one line where the size rule lives: bulk checked-in data (fixtures, demo
   assets, vendored data) gets a Read deny rule in the repo's settings, not a CLAUDE.md mention.
4. Not in scope: a CLAUDE.md per folder, per-folder subagents, sparse worktrees, any child repo.

## Failure classes and proof

- Test-author first, red on main: a 201-line fixture warns, a 200-line one does not, the check exits
  0 on a warning (a warning that fails CI is a false alarm), a missing file is a skip.
- Rule count: rule_audit's pinned counts move by exactly the new anchor; say which bucket.
- Diff touches a rule's behaviour: a fresh Sonnet reviewer reads it.

## Report

Cap 20 lines: Done, Deviations, Next. Send the green, reviewed head and branch to
"Advise the claude-settings build (2)". No question for shiv: park any in the PR body.
