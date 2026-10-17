# Every spawned agent gets the standing rules at start

## The question

Where do an agent's standing rules live, so that a brief need not retype them?

## The ruling

Owner, 2026-10-12: a SubagentStart hook injects them. `hooks/agent_brief.py` prints
`additionalContext` with the rules every brief used to carry:

- no `git stash`, `git reset`, `git checkout <path>` or `git restore`;
- push only with `git push origin HEAD:<branch>`;
- no gh call unless the brief names it;
- the role's scope;
- the report cap and label order;
- the commit trailer;
- no record path in a commit message except the `Drops-lines:` trailer.

The scope line varies by agent type: builder, test-author, reviewer, Explore,
record-writer. An unknown type gets a general line. The type is the text after the last
`:`, so a plugin type such as `my-plugin:reviewer` counts as `reviewer`. The builder scope
says to add mutants to `hooks/mutate_guard.py` when the brief asks.

Readers get five lines: reviewer, Explore, Plan and claude-code-guide never commit or push.
They get no push line, no trailer line and no record-path line. Writers and the general
case get all eight.

The hook is advisory. On an internal error it prints no context, writes one `agent_brief:`
line to stderr, and exits 0.

## Why

Every brief this session retyped the same seven lines. A brief that forgot one let an agent
stash, or push in the wrong form. Found 2026-10-12 while reading the hooks reference:
`additionalContext` on SubagentStart lands in the agent's context before its first prompt.

## What protects it

`hooks/test_agent_brief.py`: 45 cases for the output shape, each rule, the per-type scope
line, the general line, and exit 0 on junk input. CI steps in `gates`, `gates-macos` and
`gates-windows-rest`; a REQUIRED entry in `lint/test_windows_split.py`.

## Holes, named

Debts: `agent-brief-text-copy-drifts` (the hook text copies the rules, and no check reads the copy), `agent-plan-scope-line-general` (Plan and claude-code-guide get the general scope), `agent-brief-crash-silent` (a crashed hook leaves no visible trace). `agent-brief-no-matcher` (every agent type gets the context, because the hook has no matcher).

Kind: build
Plan: decisions/agents-get-standing-rules.md#the-ruling (all)
Home: hooks/agent_brief.py
