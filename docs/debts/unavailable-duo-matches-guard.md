# The guard matches an unavailable phone by its name

- **What.** The simulator name match in `hooks/guard.py` also counts devices that are unavailable, such as a deleted phone that is still listed. A launch can then be judged against a device that cannot boot. Review finding F7, pre-existing.
- **Where.** `hooks/guard.py`, the simulator name match (near line 7044).
- **Decision.** `sim-lease-tool`, the lease tool that finds each phone by its name.
- **Retire.** A new `lint/test_sim_guard_unavailable.py`, written by the lane that closes this debt, runs a launch against a device listed as unavailable and expects the guard to refuse it.

Seen: 2026-11-25 x1
