# Low-disk guard refuses builds below 20 GB

**What waits.** Part 2 of decision build-dirs-reaped-at-agent-end, the low-disk build guard. A check in the PreToolUse rule of `hooks/guard.py` refuses a build command when the free space on the worktree's volume is below 20 GB. Build commands are `xcodebuild`, `swift build`, and similar commands. The guard keeps one named list of them.

**Why it waits.** The owner agreed to Part 1 on 2026-10-11. The owner deferred Part 2 until a threshold is measured. Build Part 1 first.

**What keeps it from being lost.** This file.

**Design.**

- The 20 GB threshold is a default. The feed-build session's figures put one native worktree at up to about 10 GB of build output, so 20 GB leaves room for about two. Those figures are unmeasured.
- If the free-space read fails, the guard allows the build. A guard that refuses on a read error blocks every build on a machine where the read breaks. The reap still runs.
- The refusal reports the free space and the threshold. Its remedy names no path to delete.
- The guard is new. It is built against the incident in decision build-dirs-reaped-at-agent-end (feed-build, 2026-10-11).

**Governing record.** `guard-that-cries-wolf-is-spent`: a guard that goes red when nothing is wrong is spent. A guard that refuses on a disk with room is a false alarm. This applies to the threshold.

**What reopens it.** Both measurements below, taken on the feed-build machine, and the owner's word on a threshold:

- The build output that one worktree holds once Part 1 reaps are live.
- The free space at which a build first fails with ENOSPC.

A build that fails with ENOSPC while Part 1 is live also reopens it.

**Proof owed when built.**

- A guard case that goes red on the old guard. A build command below 20 GB is refused. The same command above it is allowed. A build with a failed free-space read is allowed.
- A build refused on a disk with room reopens this item.
