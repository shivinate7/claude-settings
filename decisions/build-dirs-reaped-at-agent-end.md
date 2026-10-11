# Build folders are reaped at agent end

## Question

How do agent worktrees stop filling the disk with build output?

## Ruling

Owner ruling, 2026-10-11, labeled "Agent-end hook + low-disk guard". The ruling has two parts.

### Part 1. The agent-end reap deletes build folders

`janitor/agent_end_reap.py` (SubagentStop) also deletes build folders in the finished agent's own worktree. The folders are:

- `native/build`
- `.build`
- `DerivedData`
- each name in the `buildDirs` list of `.claude/janitor.json`

The three default folders always apply. `buildDirs` adds names. It cannot remove a default. The key name `buildDirs` is this record's choice. The owner left the name open.

The gates are the process reap's gates. If each gate below gives a confirmed yes, the reap deletes the folder:

1. The target is `<primary>/.claude/worktrees/<name>`, and it exists.
2. The target is not a primary checkout.
3. No live session has a cwd inside the target (`guard.worktree_live_session`).
4. No process has a cwd inside the folder. The batch read of the process reap gives these cwds.
5. The reap never follows a link.
6. Any read that cannot tell means keep.

Name matching, proposal for the owner to confirm:

- A name with `/`, such as `native/build`, matches one path under the worktree root.
- A bare name, such as `.build` or `DerivedData`, matches at any depth under the worktree. The search never crosses a link. This matches `DegenKit/.build`.

A root-only match misses `DegenKit/.build`. By the owner's figures, that is about 40% of a native worktree's build output.

Other proposals, for the owner to confirm:

- A `buildDirs` value that is not a list of strings deletes no build folder in that repository, defaults included. `sweep.read_optout` validates `.claude/janitor.json`. The builder extends it and adds no second reader.
- A link named as a build folder is kept, not removed.

### Part 2. The guard refuses builds on a low disk

A check in the `hooks/guard.py` PreToolUse rule refuses a build command when the free space on the worktree's volume is below a threshold. Build commands are `xcodebuild`, `swift build`, and similar commands. The guard keeps one named list of them.

- Threshold, proposal for the owner to confirm: 20 GB. By the owner's figures, one native build holds about 10 GB. 20 GB leaves room for about two.
- Open question, not ruled: when the free-space read cannot tell, the guard allows or refuses. This record does not choose.
- The refusal reports the free space and the threshold. Its remedy names no path to delete.

The guard is a new guard, built against the incident below, as the rules require. A guard that refuses on a disk with room is a false alarm. `guard-that-cries-wolf-is-spent` applies to the threshold.

## Incident

Feed-build, 2026-10-11. The owner reported these figures. This record did not measure them.

- Each native agent built the iOS app in its own worktree, about 10 GB each. `native/build` held about 5.6 GB. `DegenKit/.build` held about 4 GB.
- About 77 of 194 worktrees held build output, about 330 GB. The scratchpad held 42 GB of derived data.
- The disk reached 540 MB free. `native-check` failed with ENOSPC.
- The daily janitor skips registered worktrees. The agent-end reap only stops processes. Nothing deleted build output.

The owner's figures do not add up. 77 worktrees at about 10 GB is about 770 GB, not 330 GB. Either not every worktree held about 10 GB, or the total is wrong. Unmeasured.

## Governing records

- `agent-end-reap-stops-what-a-finished-agent-left`: the process reap. Part 1 adds to it. Its gates and its 60 s reap timeout apply here.
- `the-janitor-is-one-machine-wide-sweep`: the sweep skips registered worktrees. Its `huskNames` key covers unregistered folders only, so this record does not reuse it.
- `unattended-sweep-stops-proven-orphans`: a sweep stops only proven orphans.
- `guard-that-cries-wolf-is-spent`: a guard that goes red when nothing is wrong is spent.

## Named limits

- A resumed agent rebuilds cold. Part 1 deletes its build output at the first agent end.
- A crashed agent whose SubagentStop never fires keeps its build output. Only Part 2 catches it.
- The 42 GB of derived data in the scratchpad is outside every worktree. Part 1 never touches it. Only Part 2 slows its growth.
- Unmeasured: whether deleting about 10 GB of build files fits in the 60 s hook cap. A slow delete can hit the cap, as the process reap's timeout did. This record does not design a fix.

## Proof owed

- A test that goes red on the old reaper. A build folder in `agent-<A>` is deleted. The same folder in the primary checkout is kept. A bare `.build` at depth is deleted. A link named as a build folder is kept. A folder with a process inside is kept. A bad `buildDirs` value deletes nothing.
- One mutant per refusal, as the process reap record requires.
- A guard case that goes red on the old guard. A build command below the threshold is refused. The same command above it is allowed.
- A timed run that deletes a worktree holding about 10 GB of build output, under 60 s.

## What reopens it

- A reap that ends in `hook_cancelled` or `timedOut: true`.
- A folder deleted outside the gates, or a link followed.
- A build refused on a disk with room.
- A build that fails with ENOSPC while Part 2 is on.
- The owner's figures prove wrong.

## Scope

This record changes no code. The builder extends `janitor/agent_end_reap.py`, `sweep.read_optout`, and `hooks/guard.py`. The "Leftover folders" section of `janitor/GUIDE.md` needs the `buildDirs` key after the code lands.
