# The lock form with no start time has no pid-reuse check

- **What.** The lock `claude agent agent-<id> (pid N)`, with no start time, has no pid-reuse check. The sweep frees it when pid N is dead. A dead host whose pid a live process now holds keeps its lock. The tree stays until that process exits. That is the safe side.
- **Where.** `janitor/sweep.py`, added by lane `wt-reap`: `stale_agent_lock_verdict`, the branch where no start time is read.
- **Decision.** `the-janitor-is-one-machine-wide-sweep` (the stale agent lock section, which now names this form).
- **Retire.** The owner accepts the keep in the janitor decision, or this form gets a time to compare with. Check: a case in `janitor/test_sweep.py` for a dead host whose pid a live process holds, with the result the owner names.
