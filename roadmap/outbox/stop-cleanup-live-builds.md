# Outbox: Stop cleanup deleting live build folders

- PR 720 (keep build folders while a process runs in the agent worktree): green and reviewed, head f2067ab, still a draft. Two direct tests of agent_end_reap.reap_build_dirs(wt, cwds) now kill the two mutants that survived; before the tests both survived, after them 5 and 3 tests go red. Local checks pass: janitor unittest, the full janitor mutation run (175 of 175 killed, 1 Windows-only skip), and ste-changed (builder opus, reviewer opus, round 1 clear). Ready for the next batch.
- Note (optional, not a debt): mutate_sweep.py still tags the two mutants posix. The new tests need no POSIX process, so dropping the tag would let Windows prove the realpath/normcase cwd match.
