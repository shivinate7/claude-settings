# Plan: two agent-state gaps found in excel-ui-kit, 2026-11-11 and 2026-11-12

This report answers two read-only incident questions from an excel-ui-kit session. Part 1: a
builder agent overwrote its coordinator's handoff. Part 2: the sweep keeps finished agent worktrees
forever on Windows. Code is cited at main `2deb827ad` (Merge pull request 2713, batch-103). No code
or setting changed. "Unknown" marks a fact no read confirmed. Each part ends with a proposed lane,
not built.

## Part 1: an agent overwrote its coordinator's handoff

### What happened

The coordinator session was `d358e6f5` in excel-ui-kit. Its builder agent was `a1634141822b8dc54`,
the chart-grids builder, a Sonnet agent in its own worktree. Times are from the agent's transcript
(`~/.claude/projects/<excel-ui-kit>/d358e6f5-…/subagents/agent-a1634141822b8dc54.jsonl`).

| Time (CST) | Event |
| --- | --- |
| 17:18:57 | The builder's PreCompact hook ran with the coordinator's session id. It rewrote the coordinator's digest and state record. |
| 17:20:26 | The builder auto-compacted (`trigger: auto`, about 468k tokens before). |
| 17:20:26 | The SessionStart compact hook (`precompact_handoff.py --reorient`) printed: "Your handoff is ~/.claude/handoffs/d358e6f5-….md. Rewrite it whole." |
| 17:20:53 | The builder sent a Write to that path. The guard rule `handoff-checked-stamp` refused it, because it changed premise stamps with no proof. |
| 17:21:03 | The builder tried `cat > …` from Bash. The worktree-isolation check refused it by chance, as "too complex to verify". |
| 17:21:11 | The builder sent the Write again with every stamp set to "Checked never". It passed and replaced the coordinator's handoff. |

The cause: an agent shares its parent's `session_id`. Every handoff hook keys its paths on
`session_id` alone, so an agent's own compaction runs the parent's handoff flow.

The live copy of claude-settings was 126 commits behind main at the time. Each finding below
holds on main too.

### 1. Hooks that ask for a handoff write

| Hook (event) | Asks for | Inside an agent? | Agent check today |
| --- | --- | --- | --- |
| `precompact_handoff.py --reorient` (SessionStart compact) | Rewrite the handoff | Yes: it fired in this incident | None (`_run_reorient`) |
| `precompact_handoff.py` (PreCompact) | Nothing; writes the digest and state record | Yes: it fired at 17:18:57 | None (`run_precompact`) |
| `reread_check.py --post-compact` (PostCompact) | Nothing; sets the unread-handoff flag | Unknown; it is keyed the same way | None |
| `precompact_handoff.py --nudge` (Stop) | Rewrite the handoff at a context-size step | No: agents fire SubagentStop, and no SubagentStop hook is wired | It skips agent entries (`isSidechain`) when it counts tokens |
| `feedback_guard.py` (Stop) | "put open standing ids in the handoff" | No: Stop only | None needed |
| `reread_check.py --stop` and guard rule `handoff-unread` | Read the handoff, not write it | The guard skips an agent's call (`agent_id`) | Yes |

### 2. Nothing refuses an agent's write to the handoff

- Guard rule `handoff-sections` (a handoff write must keep every section) judges the file's
  sections, not who writes it.
- Guard rule `handoff-checked-stamp` (a stamp change needs proof) judges stamps. A write with
  "Checked never" stamps passes. That is how the 17:21:11 write passed.
- Neither rule judges a shell write (`cat >`, `tee`, `Set-Content`) to the handoff. The worktree
  check stopped the 17:21:03 try only because the command was long.

### 3. Other per-session files an agent overwrites the same way

- `state/handoff/<sid>.digest.md` and `<sid>.json`: overwritten in this incident. The `.json` now
  names the builder's worktree as `repo`. The coordinator's next post-compaction prompt would point
  at the builder's digest.
- `state/handoff/<sid>.reread`: an agent's PostCompact sets the coordinator's unread flag, if
  PostCompact fires inside agents (unknown). The coordinator is then refused until it reads a
  handoff the agent may have rewritten.
- `state/handoff/<sid>.nudge.json` and `handoffs/<sid>.inbox.*`: safe. Only Stop and
  UserPromptSubmit write them, and neither fires inside an agent.

### 4. Proposed fix

1. A new guard rule, `handoff-agent-write`, beside `handoff-sections` in `hooks/guard.py`. It
   refuses a Write, Edit or MultiEdit to `<config dir>/handoffs/<session_id>.md` when the call
   carries a valid `agent_id`. It covers the shell-write form too, or files that form as a debt.
   Guard calls from an agent carry `agent_id` (the comment above `agent_home_record_path` in
   `hooks/guard.py` says so).
2. Second step, once a payload is captured: `--reorient`, PreCompact and PostCompact skip an
   agent's run. Unknown today: whether those three payloads carry `agent_id` inside an agent.
   `transcript_path` cannot tell: the digest built at 17:18:57 holds the coordinator's text, so the
   payload named the coordinator's transcript. An agent's `cwd` under `.claude/worktrees/agent-*`
   tells only for agents with a worktree.

### 5. Test that goes red on main

- The incident's Write: path `<config dir>/handoffs/<sid>.md`, content with every section,
  `agent_id: "a1634141822b8dc54"`. Expect deny. Main allows it.
- The same Write with no `agent_id`. Expect allow, on main and after the fix.

## Part 2: the sweep keeps finished agent worktrees forever on Windows

### What happened

In excel-ui-kit on 2026-11-12 at 10:00 CST, 4 agent worktrees were clean and merged into main. Each
had the lock `claude agent agent-<id> (pid 28184)`, with no start time. `sweep.py --attended
--fast --confirm` kept all 4 as `locked: …`. The session removed 3 by hand.

### Cause: pid reuse, not a sibling process

The question as asked was: the holder pid 28184 is a sibling of the session's process, and
something re-takes the lock on resume. Both parts are wrong.

- The one lock left, `.git/worktrees/agent-a4f72b855ecd15b4b/locked`, was written on 2026-11-11
  at 12:34 CST. Nothing rewrote it on resume.
- pid 28184 today is an Electron helper of the desktop app
  (`claude.exe --type=utility --utility-sub-type=node.mojom.NodeService`), started 2026-11-12 at
  09:30. It is not a Claude Code process.
- So the Claude Code process that held pid 28184 on 2026-11-11 took the lock and later exited.
  Windows then gave its pid to the new helper.

Why the sweep keeps the tree (`janitor/sweep.py`):

- `stale_agent_lock_verdict` frees a lock with no start time only when its pid is dead. Here the
  pid is alive (the helper), so it returns False. Its docstring names this limit.
- `own_agent_lock_verdict` frees a live holder only when it is the sweep or an ancestor. 28184 is
  neither, so it returns False.
- `--fast` is not the cause. `batch` is set in fast mode; it is None only in tier1 or when the
  `merged_batch` read fails. The lock check runs before any `batch` test in `decide_worktree`.

### Answers

1. Who takes the lock: Claude Code's Agent tool, with the pid of the Claude Code process that ran
   the agent (decision `the-janitor-is-one-machine-wide-sweep`, the janitor is one machine-wide
   sweep). Nothing re-takes it on resume: the lock file's write time is 2026-11-11 12:34 CST.
2. What the rule needs: no sibling, same-parent or session-id test. It needs a pid-reuse check for a
   lock with no start time. The lock file's own write time can stand in for the missing start time.
3. Existing record: the debt note `no-start-lock-has-no-pid-check` (a lock with no start time has
   no pid-reuse check) in `docs/debts/notes.md`. It is rated "rare and harmless". This incident is
   the real case, so by rule `roles-findings-are-debts-or-notes` (a note becomes a debt after a
   real incident) it becomes a debt.
4. A live session's tree: still kept. A live holder started before it wrote its lock, so the new
   check keeps it. Behind that, `git_reads.worktree_live_session` (any live session inside) and the
   sweep's pre-removal process check (any process inside) each keep a live tree.

### Proposed fix

Pass the lock file's write time (`<git-dir>/locked`) to `stale_agent_lock_verdict`. For a lock with
no start time, return True when the holder process started more than `SESSION_LIVE_TOLERANCE_MS`
after that write time. An unreadable write time returns None, which keeps the tree.

### Test that goes red on main

- A worktree locked with `claude agent agent-x (pid <test pid>)`, its `locked` file's write time
  set one day before the test process started. Expect True. Main returns False.
- Control: a `locked` file written after the holder started. Expect False, on main and after the
  fix.

## Lanes proposed

| Lane slug | Change | Roles |
| --- | --- | --- |
| `handoff-agent-write` | Part 1, step 1: the guard rule and its red test | test-author, builder, reviewer |
| `sweep-lock-age` | Part 2: the lock-age check and its red test; the note becomes a debt | test-author, builder, reviewer |

Both change a guard's or check's verdict, so each needs a review before merge. Neither is started.
The owner decides.
