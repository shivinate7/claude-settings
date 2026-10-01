# The sweep preview time is unmeasured

**What waits.** One full `janitor/sweep.py` preview took 24 minutes in review. Nobody has timed
it since.

**Why it waits.** A timing run needs the machine to itself for about 25 minutes. The owner
cannot give that time yet.

**The idea, UNMEASURED.** The probable cause was one `lsof` call per pid on macOS, about 25 s
for each worktree that `decide_worktree` judged. `processes_in` now makes one `lsof -d cwd`
call per check. These still read one pid at a time: `decide_listener` (`process_cwd`),
`hooks/agent_end_reap.py` (`process_cwd`), and `find_dead_rooted` and `find_loose_processes`
(`process_command`).

**Trigger that brings it back.** The owner gives a free machine, or a preview feels slow again.
Time one preview on `main`. If it is still slow, move the remaining per-pid reads to one table.

**Owner.** The claude-settings orchestrator that takes the next janitor change.
