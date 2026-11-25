# Every spawned agent gets the standing rules at start

## The ruling

Owner, 2026-10-12: a SubagentStart hook injects the standing rules, so a brief need not retype them. `hooks/agent_brief.py` prints `additionalContext` with the lines below. Two standing lines carry the git bans, for every agent type. The first bans the stash verb everywhere. The second bans, outside the agent's own worktree, the discarding resets, a checkout of a path, and the restore verb. Inside its own worktree an agent may run those. The stash stack is shared by every worktree, and the other acts lose work only in a shared tree; the owner's October rulings allow them inside an agent's own worktree (decision `agent-worktree-discard-is-noted`). Owner, 14:12 CST 2026-11-23: "yes drop the line then". The owner's "yes drop the line then" dropped the ban on a reset. The line the hook prints now is narrower than that: it bans only the discarding resets, and only outside the agent's own worktree. Basis: asked which form to keep, the owner said at 23:04 CST 2026-11-24, relayed by the Sim Manager session: "i actually dont know, id have a blind opus agent decide and a refuter on it too". That agent's verdict clashed with the owner's October rulings (an agent may discard work inside its own worktree) and was withdrawn; the lane picked this form because it agrees with those rulings. A pick, not an owner ruling. The owner may reverse it.

The hook prints these lines, in this order. A line marked every type goes to every agent type. A line marked writing types only goes to every type outside the read-only set: reviewer, Explore, Plan, claude-code-guide, design-reviewer and refuter. An unknown type writes. Type names match ignoring case.

- (every type) Standing rules for this agent:
- (every type) Never run git stash.
- (every type) Outside your own worktree, never run git reset with one of the flags --hard/--merge/--keep, git checkout of a path, or git restore.
- (writing types only) Push only with: git push origin HEAD:<branch>.
- (every type) Make no gh call unless your brief names it.
- (every type) The scope line. Each type below has its own line. A type with no line of its own gets the general line.
  - builder: Scope: builder. Never edit tests or test config. A mutant goes to a test-author. Report a test change you need.
  - test-author: Scope: test-author. Edit tests and test config only. Never edit product code.
  - reviewer: Scope: reviewer. Never edit, write, stage, commit, or push. Read and run checks only.
  - Explore: Scope: Explore. Never edit. Read and search only.
  - record-writer: Scope: record-writer. Edit Markdown (*.md) files only. Report any other change needed.
  - designer: Scope: designer. Edit files in the repo's design folder only. Report any other change needed. Your brief names your designer kind: blind, informed or directed. In a blind designer, never read the current screen, its code, its screenshots, its mockups, or the repo's design spec and tokens.
  - design-reviewer: Scope: design-reviewer. Never edit, write, stage, commit, or push. Read and render only.
  - refuter: Scope: refuter. Never edit, write, stage, commit, or push. Read only.
  - general, for Plan, claude-code-guide and an unknown type: Scope: do only what your brief names. A builder never edits tests; a test-author never edits product code; a reviewer and Explore never edit; a record-writer edits Markdown only.
- (every type) Report in 25 lines or fewer unless the brief sets a cap. Order: Done, Deviations, Input Needed, Next.
- (writing types only) End each commit message with: Co-Authored-By: <model> <noreply@anthropic.com>
- (writing types only) Name no record path in a commit message. The only exception is the Drops-lines: trailer.
- (writing types only) Before each commit, run git diff --cached --stat; if it names a file you did not change this round, commit nothing and report it (decision `lanes-start-in-tool-worktrees`: lanes start only in the tool's own worktrees).
- (writing types only) Before you end, stop each server you started, by the $! from the same call or through the harness.
- (every type, when this repo's layout reads) First note rule: a new or edited note is its own file, the note folder then <slug>.md, one line `- <slug>: <text>`. The slug is the file name, within the length MAX in lint/check_record_slugs.py sets, and not digits only. Second note rule: the old notes file takes deletes only: add no line to it and edit none.
- (every type, when .github/stamp.json sets cite.form) Cite a record in this repo's form, one form per record kind, joined by commas. Any other wrapper around a slug stays dead text.

- The type is the text after the last `:`, so `my-plugin:reviewer` counts as `reviewer`. The builder scope line says `A mutant goes to a test-author.` Owner ruling, 2026-11-08 17:19 CST (waiting-page item 447 a): mutants are test content.
- Readers (the six read-only types above) get the six every-type lines, plus the note and cite lines when they apply. They never commit or push, so they get no push, trailer, record-path, diff or server line. Writers and the general case get all eleven fixed lines, plus the note and cite lines when they apply.
- The hook is advisory. On an internal error it prints no context, writes one `agent_brief:` line to stderr, and exits 0.

Why: a brief that forgot one line let an agent stash, or push in the wrong form. `additionalContext` on SubagentStart lands in the agent's context before its first prompt.

Protected by `hooks/test_agent_brief.py`, run in `checks-hooks`, `checks-macos` and `checks-windows-rest`, with a REQUIRED entry in `lint/test_windows_split.py`.

Kind: build
Plan: docs/decisions/agents-get-standing-rules.md#the-ruling (all)
Home: hooks/agent_brief.py, the COMMON list
