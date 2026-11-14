# An Office process the main session starts can end at an agent's stop

- **What.** On Windows, a hidden Office process that the main session starts while an agent runs looks like that agent's own. The Office adapter sees it in the after list but not the before list. So it ends at the stop (round 2 review, finding 2). The ruling says an unclear owner is reported, never ended. The harm: a person's own Excel or Word ends.
- **Where.** `hooks/agent_procs.py`, `office_candidates`, and `janitor/agent_end_reap.py`, the Office stop stage. Unmeasured on Windows.
- **Decision.** `none`. Step `agent-owned-processes` and its ruling `own-agent-owned-processes` name the report-never-end rule for an unclear owner.
- **Retire.** A case in `hooks/test_agent_procs.py` shows an Office pid with no parent or start link to the stopping agent is reported and not ended. A solo agent's own pid still ends. The suite passes.
