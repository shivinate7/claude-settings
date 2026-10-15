# A commit message from stdin is never read

- **What.** A message from `-F -` stdin is never read, so a prose cite there passes. This predates the Drops-lines exemption. The undo lint grants no excuse there.
- **Where.** The message reader in `hooks/guard.py` (`cited_record_path`).
- **Decision.** `drops-lines-trailer-exempt` (a commit's Drops-lines trailer may name a record path).
- **Retire.** The guard reads a `-F -` message, and a case refuses a prose cite there.
