# Build folders are reaped at agent end

## Question

How do agent worktrees stop filling the disk with build output?

## Ruling

Owner ruling, 2026-10-11, labeled "Agent-end hook + low-disk guard". The ruling has two parts. The orchestrator set the defaults in this record. The owner may change any default.

### Part 1. The agent-end reap deletes build folders

`janitor/agent_end_reap.py` (SubagentStop) also deletes build folders in the finished agent's own worktree. The folders are:

- `native/build`
- `.build`
- `DerivedData`
- each name in the `buildDirs` list of `.claude/janitor.json`

The three default folders always apply. `buildDirs` adds names. It cannot remove a default. Default key name: `buildDirs`.

If each gate below gives a confirmed yes, the reap deletes the folder:

1. The target is `<primary>/.claude/worktrees/<name>`, and it exists.
2. The target is not a primary checkout.
3. No live session has a cwd inside the target (`guard.worktree_live_session`).
4. No process has a cwd inside the folder. The batch read of the process reap gives these cwds.
5. The reap never follows a link.
6. Any read that cannot tell means keep.

Delete in two steps:

1. The reap renames each proven folder to a sibling trash name inside the same worktree. The rename stays on one volume, so it is one fast step.
2. The reap starts a detached child that deletes the trash. The hook does not wait for the child.

A later reap or the janitor deletes trash names that a child left. If a trash name matches the trash pattern and the gates above hold for it, the janitor deletes it. The builder sets the pattern.

Name matching:

- A name with `/`, such as `native/build`, matches one path under the worktree root.
- A bare name, such as `.build` or `DerivedData`, matches at any depth under the worktree. The search does not cross a link. This matches `DegenKit/.build`.

A root-only match misses `DegenKit/.build`. By the feed-build session's figures, that is about 40% of the build output of a native worktree.

Other defaults:

- A `buildDirs` value that is not a list of strings deletes nothing, defaults included. `sweep.read_optout` validates `.claude/janitor.json`. The builder extends it and adds no second reader.
- A link named as a build folder is kept, not removed.

### Part 2. The guard refuses builds on a low disk

A check in the `hooks/guard.py` PreToolUse rule refuses a build command when the free space on the worktree's volume is below 20 GB. Build commands are `xcodebuild`, `swift build`, and similar commands. The guard keeps one named list of them.

- The 20 GB threshold is a default. The feed-build session's figures put one native worktree at up to about 10 GB of build output. So 20 GB leaves room for about two.
- If the free-space read fails, the guard allows the build. A guard that refuses on a read error would block every build on a machine where the read breaks. The reap still runs.
- The refusal reports the free space and the threshold. Its remedy names no path to delete.

The guard is a new guard, built against the incident below, as the rules require. A guard that refuses on a disk with room is a false alarm. `guard-that-cries-wolf-is-spent` applies to the threshold.

## Incident

Feed-build, 2026-10-11. The feed-build session reported these figures. This record did not measure them.

- Native agents built the iOS app in their own worktrees. A worktree held up to about 10 GB. `native/build` held about 5.6 GB. `DegenKit/.build` held about 4 GB.
- About 77 of 194 worktrees held build output. The scratchpad held 42 GB of derived data.
- The disk reached 540 MB free. `native-check` failed with ENOSPC.
- The daily janitor skips registered worktrees. The agent-end reap only stops processes. Nothing deleted build output.

Arithmetic: the 77 worktrees held about 330 GB in total, and each held up to about 10 GB. The per-worktree sizes varied. Unmeasured: the size of each worktree.

## Governing records

- `agent-end-reap-stops-what-a-finished-agent-left`: the process reap. Part 1 adds to it. Its gates and its 60 s reap timeout apply here.
- `the-janitor-is-one-machine-wide-sweep`: the sweep skips registered worktrees. Its `huskNames` key covers unregistered folders only, so this record does not reuse it.
- `unattended-sweep-stops-proven-orphans`: a sweep stops only proven orphans.
- `guard-that-cries-wolf-is-spent`: a guard that goes red when nothing is wrong is spent.

## Named limits

- A resumed agent rebuilds cold. Part 1 deletes its build output at the first agent end.
- A crashed agent whose SubagentStop never fires keeps its build output. Only Part 2 catches it.
- The 42 GB of derived data in the scratchpad is outside every worktree. Part 1 never touches it. Only Part 2 slows its growth.
- Trash names stay on disk until a later reap or the janitor deletes them.
- Unmeasured: the rename time on the feed-build machine. The hook does one rename, so the 60 s cap applies to the rename. It does not apply to the delete.

## Proof owed

- A test that goes red on the old reaper. A build folder in `agent-<A>` is renamed to trash and then deleted. The same folder in the primary checkout is kept. A bare `.build` at depth is renamed and deleted. A link named as a build folder is kept. A folder with a process inside is kept. A bad `buildDirs` value deletes nothing.
- A test that a later reap deletes a leftover trash name, and that the janitor does the same. A trash name outside the pattern is kept. A trash name with a process inside is kept.
- One mutant per refusal, as the process reap record requires.
- A guard case that goes red on the old guard. A build command below 20 GB is refused. The same command above it is allowed. A build with a failed free-space read is allowed.
- A timed run. The hook returns after the rename, under 60 s, on a worktree holding about 10 GB of build output.

## What reopens it

- A reap that ends in `hook_cancelled` or `timedOut: true`.
- A folder deleted outside the gates, or a link followed.
- A build refused on a disk with room.
- A build that fails with ENOSPC while Part 2 is on.
- Trash names that a later reap or the janitor does not delete.

## Scope

This record changes no code. The builder extends `janitor/agent_end_reap.py`, `sweep.read_optout`, and `hooks/guard.py`. The "Leftover folders" section of `janitor/GUIDE.md` needs the `buildDirs` key after the code lands.
