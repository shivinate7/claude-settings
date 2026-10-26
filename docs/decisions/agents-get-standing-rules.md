# Every spawned agent gets the standing rules at start

## The ruling

Owner, 2026-10-12: a SubagentStart hook injects the standing rules, so a brief need not retype them. `hooks/agent_brief.py` prints `additionalContext` with:

- no `git stash`, `git reset`, `git checkout <path>` or `git restore`;
- push only with `git push origin HEAD:<branch>`;
- no gh call unless the brief names it;
- the role's scope;
- the report cap and label order;
- the commit trailer;
- no record path in a commit message except the `Drops-lines:` trailer;
- before it ends, a writer stops each server it started, by the `$!` from the same call or through the harness.

- The scope line varies by agent type: builder, test-author, reviewer, Explore, record-writer. An unknown type gets a general line. The type is the text after the last `:`, so `my-plugin:reviewer` counts as `reviewer`. The builder scope says to add mutants to `hooks/mutate_guard.py` when the brief asks.
- Readers (reviewer, Explore, Plan, claude-code-guide) get five lines: they never commit or push, so no push, trailer, record-path or server line. Writers and the general case get all nine.
- The hook is advisory. On an internal error it prints no context, writes one `agent_brief:` line to stderr, and exits 0.

Why: a brief that forgot one line let an agent stash, or push in the wrong form. `additionalContext` on SubagentStart lands in the agent's context before its first prompt.

Protected by `hooks/test_agent_brief.py`, run in `checks`, `checks-macos` and `checks-windows-rest`, with a REQUIRED entry in `lint/test_windows_split.py`.

Kind: build
Plan: docs/decisions/agents-get-standing-rules.md#the-ruling (all)
Home: hooks/agent_brief.py
