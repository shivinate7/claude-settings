# Build folders are reaped at agent end

## Ruling

Owner, 2026-10-11, "Agent-end hook + low-disk guard". The orchestrator set the defaults. The owner may change any default. The owner agreed to Part 1 and deferred Part 2, the low-disk build guard, to deferred item `build-disk-guard`.

### Part 1. The agent-end reap deletes build folders

`janitor/agent_end_reap.py` (SubagentStop) also deletes build folders in the finished agent's own worktree: `native/build`, `.build`, `DerivedData`, and each name in the `buildDirs` list of `.claude/janitor.json`. The three defaults always apply. `buildDirs` adds names and cannot remove a default.

The reap deletes a folder only when each gate gives a confirmed yes. Any read that cannot tell means keep.

1. The target is `<primary>/.claude/worktrees/<name>`, and it exists.
2. The target is not a primary checkout.
3. No live session has a cwd inside the target (`guard.worktree_live_session`).
4. No process has a cwd inside the folder. The batch read of the process reap gives these cwds.
5. The reap never follows a link.

Delete in two steps. First, the reap renames each proven folder to a sibling trash name inside the same worktree, on one volume, so it is one fast step. The trash pattern is `<name>.reap-trash-<12 hex digits>`. Second, it starts a detached child that deletes the trash, and the hook does not wait. A later reap or the janitor deletes trash names that a child left, when the gates hold for them.

Name matching: a name with `/`, such as `native/build`, matches one path under the worktree root. A bare name, such as `.build` or `DerivedData`, matches at any depth under the worktree, and the search does not cross a link. This matches `DegenKit/.build`, about 40% of a native worktree's build output by the feed-build session's figures.

- A `buildDirs` value that is not a list of strings deletes nothing, defaults included. `sweep.read_optout` is the one reader of `.claude/janitor.json`.
- A link named as a build folder is kept, not removed.
- Windows deletes the same as macOS and Linux (owner, 2026-10-12). `sweep.is_link` is the one link test: a symlink, or a reparse point read from `os.lstat`, because `os.path.islink` never sees a junction. A junction named as a build folder is kept. A junction inside a build folder is unlinked, and its target is untouched. A worktree that is itself a junction is not scanned.
- The hook stops its build-folder scan after 20 s and keeps what it did not reach. The hook's own limit is 60 s.
- The sweep report shows a `trash` line for each trash folder it finds, with its action and reason. The sweep deletes leftover trash only in registered, non-primary worktrees directly under `.claude/worktrees`.

Why: native agents built the iOS app in their own worktrees, up to about 10 GB each. The disk filled and `native-check` failed with ENOSPC. The daily janitor skips registered worktrees and the agent-end reap only stopped processes, so nothing deleted build output.

Governing records: `agent-end-reap-stops-what-a-finished-agent-left` (the process reap; its gates and 60 s timeout apply here), `the-janitor-is-one-machine-wide-sweep` (its `huskNames` key covers unregistered folders only, so it is not reused), `unattended-sweep-stops-proven-orphans`.

## Named limits

- A resumed agent rebuilds cold.
- A crashed agent whose SubagentStop never fires keeps its build output until `build-disk-guard` lands. So does the derived data in the scratchpad, which is outside every worktree.
- `shutil.rmtree` on Windows has no symlink-attack guard, and POSIX has one. A link swapped in after the rename and before the child's delete is not covered on Windows.
- No mutant covers the `is_link(target)` guard in `reap_build_dirs`, nor the `is_link` refusals in `trash_verdict` and `find_trash`. Their cases are Windows-only. The `DELETE_CHILD` check cannot go red, because `rmtree` refuses a top-level junction by itself.
- Trash names stay on disk until a later reap or the janitor deletes them. Unmeasured: the rename time on the feed-build machine.

Reopen on a reap that ends in `hook_cancelled` or `timedOut: true`, a folder deleted outside the gates, a link followed, or trash names that nothing deletes.

Kind: process
Home: janitor/agent_end_reap.py
