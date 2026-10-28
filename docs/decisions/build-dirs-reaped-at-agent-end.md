# Build folders are reaped at agent end

## The ruling

Owner, 2026-10-11: the agent-end reap also deletes build folders. The low-disk build guard is deferred to debt
`build-disk-guard`.

`janitor/agent_end_reap.py` (SubagentStop) deletes build folders: `native/build`, `.build`, `DerivedData`, and each name in the
`buildDirs` list of `.claude/janitor.json`. The three defaults always apply. `buildDirs` adds names and cannot remove a default.

Build folders follow the worktree's 30-minute idle clock (roadmap step c157, cleanup never deletes a live agent's build folders). The ending agent's own tree keeps its build folders at
its own end, because a finished agent is often resumed there and would rebuild from nothing. A later agent end reaps them. The reap
deletes a folder only when each gate gives a confirmed yes. Any read that cannot tell means keep.

1. The tree is another `<primary>/.claude/worktrees/agent-*` tree, not the ending agent's own tree and not a primary checkout.
2. The tree is idle 30 minutes or more (`sweep.worktree_idle_seconds`, read before any `git status`). An unreadable idle keeps.
3. The tree holds no live lock. Only a lock `sweep.stale_agent_lock_verdict` proves stale lets the reap go on.
4. No live session has a cwd inside the tree (`guard.worktree_live_session`).
5. No process has a cwd anywhere in the tree. The reap stops no process there. A build runs from the worktree root and writes
   into the folder, so a cwd check on the folder alone deleted live builds (likely risk, 2026-10-27).
6. The reap never follows a link. A link named as a build folder is kept.

- The worktree stage runs the build pass on each tree it keeps (dirty, unpushed, and so on). A tree it removes whole needs no pass.
- The pass shares the stage deadline (`WORKTREE_SECONDS`, `HOOK_BUDGET`). A tree the deadline does not reach keeps its folders.
- Each tree's row in the payload log carries `buildDirs` (folders renamed) or `buildDirsKept` (why not).
- Delete in two steps. The reap renames each proven folder to a sibling trash name in the same worktree. Then a detached child
  deletes the trash, and the hook does not wait. Trash a child left follows the same gates: a later reap or the janitor deletes it.
- A name with `/` matches one path under the worktree root. A bare name matches at any depth under the worktree, and the search
  does not cross a link.
- A `buildDirs` value that is not a list of strings deletes nothing, defaults included. `sweep.read_optout` is the one reader of
  `.claude/janitor.json`.
- Windows deletes the same as macOS and Linux (owner, 2026-10-12). `sweep.is_link` is the one link test.
- The hook stops its build-folder scan after 20 s and keeps what it did not reach. The hook's own limit is 60 s.
- The sweep deletes leftover trash only in registered, non-primary worktrees directly under `.claude/worktrees`.

Reason: native agents built the iOS app in their own worktrees. The disk filled and `native-check` failed with ENOSPC. The daily
janitor skips registered worktrees and the agent-end reap stopped only processes. Governing records: `agent-end-reap-stops-what-a-finished-agent-left` (the process reap; its gates and 60 s timeout apply here),
`the-janitor-is-one-machine-wide-sweep` (its `huskNames` key covers unregistered folders only, so it is not reused),
`unattended-sweep-stops-proven-orphans`.

Kind: process
Home: janitor/agent_end_reap.py
