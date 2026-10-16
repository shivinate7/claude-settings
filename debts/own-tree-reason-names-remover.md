# The own-tree row names a removed remover

**What.** The hook's row for the ending agent's own tree says "left for the delayed
remover", and comments name lane wt-reap-delay. That lane is closed unbuilt (owner ruling
2026-10-16 00:47 CDT), so the text points at nothing.

**Where.** `janitor/agent_end_reap.py`, `OWN_TREE_REASON` and its comments; the
`janitor/test_sweep.py` cases that assert the text.

**Decision.** agent-end-reap-stops-what-a-finished-agent-left (what agent end removes).

**Retire.** The reason reads "own tree: kept for 30 idle min", and the cases assert it.
