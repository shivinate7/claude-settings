# A fix for a broken PR read has no recovery path

- **What.** A fix for a broken PR read is itself a PR. It meets the guards that fail closed on that read: the merge tool's own reads, and the `records-page-ready` rule, which reads the head before a ready mark. While the read is broken, those guards refuse the fix. No recovery path is built. Today the only exits are the owner's typed `override` and, for the merge tool only, starting it with `AI_AGENT` and `CLAUDECODE` unset. A guard hook cannot be started that way.
- **Where.** `hooks/guard.py`, rule `records-page-ready`. `merge/merge.py`, `Host.gh` and `read_pr`.
- **Decision.** `recovery-independent-of-state` (a recovery control must not depend on the state it recovers).
- **Retire.** Closed when a recovery path exists for a broken PR read, and a case in `merge/test_merge.py` marks a fix pull request ready while that read is broken.
