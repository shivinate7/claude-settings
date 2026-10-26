# No wait for checks after a push

- **What.** A session can report a push as done before its checks finish. The `merge-checks` guard rule stops only a merge.
- **Where.** `hooks/ci_wake.py`, which starts no wait on a push.
- **Decision.** `claude-md-shrink` (CLAUDE.md drops the prose of a rule that a guard or check enforces).
- **Retire.** A hook holds a report that names a push until the push's checks finish, or the owner accepts the gap.
