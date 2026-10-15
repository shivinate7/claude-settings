# A merge reply with state OPEN still reverts

- **What.** A `gh pr merge` reply with exit 0 and a state read of OPEN still reverts (`merge/merge.py` lines 549-550). A lagging read or a merge queue could revert a merge that landed.
- **Where.** `merge/merge.py` lines 549-550.
- **Decision.** `merge-net-retry` (what bin/merge does when a network error stops a call).
- **Retire.** A reply with exit 0 and state OPEN reads the state again before any revert, and a case pins it.
