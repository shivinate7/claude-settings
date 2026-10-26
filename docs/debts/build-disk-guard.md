# No low-disk guard refuses a build

**What.** Part 2 of `build-dirs-reaped-at-agent-end`, the low-disk build guard, is not built. A build can fill the disk (ENOSPC) before the agent-end reap runs.

**Where.** `hooks/guard.py`, the PreToolUse rule. It would refuse a build command (`xcodebuild`, `swift build`, and similar, one named list) when the free space on the worktree's volume is below 20 GB.

**Decision.** `build-dirs-reaped-at-agent-end`, reap build folders at agent end (Part 1 is live). `guard-that-cries-wolf-is-spent` governs the threshold: a refusal on a disk with room is a false alarm.

**Retire.** Take both measurements on the feed-build machine and get the owner's word on a threshold. Then build the guard against the feed-build incident of 2026-10-11, with cases that go red on the old guard:

- A build command below the threshold is refused. The same command above it is allowed.
- A failed free-space read allows the build (a refusal on a read error blocks every build where the read breaks).
- The refusal reports the free space and the threshold, and names no path to delete.

A build refused on a disk with room reopens this debt.

## Ruling

Owner, 2026-10-11: build Part 1 first. Part 2 waits until a threshold is measured. The 20 GB figure is a default, unmeasured: one native worktree holds up to about 10 GB of build output. Measure (a) the build output one worktree holds once Part 1 reaps are live, and (b) the free space at which a build first fails with ENOSPC. A build that fails with ENOSPC while Part 1 is live also reopens it.
