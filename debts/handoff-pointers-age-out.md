# Pointers and handoffs age out wrongly

- **What.** Pointers that have a handoff have no age rule. A raised `cleanupPeriodDays` still sweeps after 30 days, because `STALE_AGE` is fixed at 30 days.
- **Where.** `STALE_AGE` and the reorient sweep in the SessionStart hook.
- **Decision.** `handoff-hooks-wave-2` (clear, fork, re-read and CI wake-up).
- **Retire.** If `cleanupPeriodDays` is raised, the sweep age follows it. A case pins this, and a case pins the age rule for pointers with a handoff.
