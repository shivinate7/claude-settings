# A solo-owner merge role outlives a later create_session

- **What.** On `origin/merge-role-raw-paths` (not on main yet), `read_merge_role` checks only that the role file names this session's id, not when the role was written. So a solo-owner role recorded before a later `create_session` stays valid for `merge --confirm` and for the raw merge check. Likelihood low.
- **Where.** `read_merge_role` in `merge/merge.py` and `raw_role_hit` in `hooks/guard_merge.py`, both on `origin/merge-role-raw-paths`.
- **Decision.** `session-tiers` (which merge role each session tier holds).
- **Retire.** A role recorded before a `create_session` stops passing, and `merge/test_merge.py` holds the case.

- Fix: step:notes-reverify-flags
