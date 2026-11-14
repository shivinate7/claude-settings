# A released sim-lease holder that carries the agent's marker comes back un-ended at the stop

- **What.** At SubagentStop the reap rebuilds each marked pid as a fresh record entry with no `ended` mark, so a lease holder the agent already released with `give` reads as owned again, kind "unclear", with a start taken from lease text. Another agent's kill of a later process that reuses that pid number is then refused. Round 3 review of agent-owned-processes found it. It refuses and never allows. The two new reap tests use an unmarked holder, so they miss it.
- **Where.** `janitor/agent_end_reap.py`, the entry rebuild just before the line that keeps an existing `ended` True.
- **Decision.** `none`. The ruling `own-agent-owned-processes` makes sim-lease join the same record.
- **Retire.** A case in `janitor/test_sweep.py` runs a marked lease holder through take, give and SubagentStop, then shows `recorded_owners(pid)` is empty. The suite passes.
