# Build folders are reaped at agent end

## The ruling

Owner, 2026-10-11: the agent-end reap also deletes build folders. The low-disk build guard is deferred to debt
`build-disk-guard`.

`janitor/agent_end_reap.py` (SubagentStop) deletes build folders in the finished agent's own worktree: `native/build`, `.build`,
`DerivedData`, and each name in the `buildDirs` list of `.claude/janitor.json`. The three defaults always apply. `buildDirs` adds
names and cannot remove a default. The reap deletes a folder only when each gate gives a confirmed yes. Any read that cannot tell
means keep.

1. The target is `<primary>/.claude/worktrees/<name>`, it exists, and it is not a primary checkout.
2. No live session has a cwd inside the target (`guard.worktree_live_session`).
3. No process has a cwd inside the folder.
4. The reap never follows a link. A link named as a build folder is kept.

- Delete in two steps. The reap renames each proven folder to a sibling trash name in the same worktree. Then a detached child
  deletes the trash, and the hook does not wait. A later reap or the janitor deletes trash that a child left, when the gates hold
  for it.
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
