# The archive guard cannot read a child lane's repo until add_repo attaches it

- **What.** The archive guard cannot read a child lane's repo until `add_repo` attaches that repo to the session. On 2026-11-13 it refused three times on lane `session-mailbox-followups`. The fix was `add_repo` at 09:08 CST. The refusal now names that act, but the session still needs the repo attached before the guard can read it.
- **Where.** `hooks/guard_merge.py`, `archive_hit` and `_stranded_branch`.
- **Decision.** `session-tiers`, a lane closes only after its records pull request has landed.
- **Retire.** The guard reads a child lane's repo without a manual `add_repo`, or the refusal's remedy is mechanical. `env GUARD_FAMILY=lane-closes-after-records python3 hooks/test_guard.py` passes, and `hooks/test_guard.py` holds a case where a lane's second repo is unattached and the archive is allowed or its repo is attached by the guard.
