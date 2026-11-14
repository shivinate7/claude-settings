# A background job started in an agent's foreground call is never recorded

- **What.** An agent's foreground call carries no agent marker (`hooks/stall_watch.py`). A `&` job it starts has no marker, so the agent stop neither records nor ends it. The step agent-owned-processes ends only marked processes. Claude starts such jobs often, so a hidden process can outlive its agent.
- **Where.** `hooks/stall_watch.py`, the marker line for a foreground call, and `janitor/agent_end_reap.py`, the marker scan at the stop.
- **Decision.** `none`. The ruling `own-agent-owned-processes` says every process an agent starts.
- **Retire.** A case in `hooks/test_agent_procs.py` shows a job started with `&` in a foreground agent call is recorded to that agent and ends at its stop. The suite passes.
