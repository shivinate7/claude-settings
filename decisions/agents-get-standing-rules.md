# Every spawned agent gets the standing rules at start

## The question

Where do an agent's standing rules live, so that a brief need not retype them?

## The ruling

Owner, 2026-10-12: a SubagentStart hook injects them. `hooks/agent_brief.py` prints
`additionalContext` with the rules every brief used to carry: no `git stash`, `git reset`,
`git checkout <path>` or `git restore`; push only with `git push origin HEAD:<branch>`; no gh
call unless the brief names it; the role's scope; the report cap and label order; the commit
trailer; no record path in a commit message except the `Drops-lines:` trailer. The scope line
varies by agent type (builder, test-author, reviewer, Explore, record-writer). An unknown type
gets a general line. The hook is advisory: on any error it prints nothing and exits 0
(decision gate-hooks-fail-closed names the advisory class).

## Why

Every brief this session retyped the same six lines. A brief that forgot one let an agent
stash, or push in the wrong form. Found 2026-10-12 while reading the hooks reference:
`additionalContext` on SubagentStart lands in the agent's context before its first prompt.

## What protects it

`hooks/test_agent_brief.py`: 34 cases for the output shape, each rule, the per-type scope
line, the general line, and exit 0 on junk input. CI steps in `gates`, `gates-macos` and
`gates-windows-rest`; a REQUIRED entry in `lint/test_windows_split.py`.

## Holes, named

- The hook's text is a copy of the rules in CLAUDE.md and `agents/*.md`. When a rule changes,
  change both. The test pins the text, not the source.
- No matcher: every agent type gets the context, Plan and claude-code-guide included.
- Fail-open: a crashed hook injects nothing, with no log line.
