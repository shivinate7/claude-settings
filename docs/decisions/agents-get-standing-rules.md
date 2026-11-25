# Every spawned agent gets the standing rules at start

## The ruling

Owner, 2026-10-12: a SubagentStart hook injects the standing rules, so a brief need not retype them. The text is one home: `hooks/agent_brief.py` builds the lines from the constants `COMMON` (the fixed lines), `SCOPE` (one scope line per agent type) and `GENERAL` (the scope line for every other type). This record cites those constants and repeats no line. The lines tell each spawned agent its limits and its reporting form before its first prompt.

Each `COMMON` line is marked for every type, or for writing types only. Writing types are every type outside `READ_ONLY` (reviewer, Explore, Plan, claude-code-guide, design-reviewer and refuter). An unknown type writes. Type names match ignoring case.

The note lines come from `AGENT_FORM_RULES` in `lint/check_record_slugs.py`, filled from the repo's layout, and are given only when that layout reads. The cite line comes from `cite.form` in `.github/stamp.json`, and is given only when that file sets it.

Two standing lines carry the git bans, for every agent type. The stash line bans the stash verb everywhere. The reset line bans, outside an agent worktree (a folder under .claude/worktrees), the discarding resets (the flags `RESET_DISCARD_FLAGS` names), a checkout of a path, and the restore verb. Inside an agent worktree an agent may run those. The stash stack is shared by every worktree. The guard allows a whole-tree discard only in an agent worktree (`agent_owned_worktree` in `hooks/guard.py`): it refuses one in the main checkout and in a hand-made worktree. A named-file checkout or restore passes in any linked worktree, not in the main checkout (decision `agent-worktree-discard-is-noted`, which holds the owner's October rulings).

Owner, 14:12 CST 2026-11-23: "yes drop the line then". The lane reads these words as dropping the blanket ban on a reset; the question they answered is not in the repo. So the reset line is narrower than a blanket ban: it bans the discarding resets, a checkout of a path and the restore verb, and only outside an agent worktree.

Basis: asked which form to keep, the owner said at 23:04 CST 2026-11-24, relayed by the Sim Manager session: "i actually dont know, id have a blind opus agent decide and a refuter on it too". The blind Opus agent and its refuter did run, in the Sim Manager session. That agent's verdict clashed with the owner's October rulings (an agent may discard work inside an agent worktree) and was withdrawn. The lane picked this form because it agrees with those rulings. This is a pick, not an owner ruling. The owner may reverse it.

The commit-evidence line: asked whether untracked evidence in an agent worktree (test-result bundles) is saved outside the worktree or committed, the owner said at 14:12 CST 2026-11-23: "Commit it". Lane pick the owner may reverse: every agent that can write gets the line, a read-only agent does not.

The type is the text after the last `:`, so `my-plugin:reviewer` counts as `reviewer`. The builder scope line says `A mutant goes to a test-author.` Owner ruling, 2026-11-08 17:19 CST (waiting-page item 447 a): mutants are test content.

Readers (the six read-only types above) get the six every-type lines, plus the note and cite lines when they apply. They never commit or push, so they get no push, trailer, record-path, diff, commit-evidence or server line. Writers and the general case get all twelve fixed lines, plus the note and cite lines when they apply.

The hook is advisory. On an internal error it prints no context, writes one `agent_brief:` line to stderr, and exits 0. When the shared-tree module (`guard_shared_tree`) cannot be imported, the hook prints every other standing line and no reset line.

Why: a brief that forgot one line let an agent stash, or push in the wrong form. `additionalContext` on SubagentStart lands in the agent's context before its first prompt.

Protected by `hooks/test_agent_brief.py`, run in `checks-hooks`, `checks-macos` and `checks-windows-rest`, with a REQUIRED entry in `lint/test_windows_split.py`.

Kind: build
Plan: docs/decisions/agents-get-standing-rules.md#the-ruling (all)
Home: hooks/agent_brief.py, the COMMON list
