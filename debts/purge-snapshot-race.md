# The purge reads unexpired rows once, at its start

- **What.** The set of unexpired rows is read once, at purge start. A reap that logs the same commit later is not seen. The old-value pin on `update-ref -d` still protects a changed ref value. This was read from code and not run.
- **Where.** The unexpired-row read at the start of the purge in `janitor/sweep.py`.
- **Decision.** `purge-keeps-younger-restore-ref` (the purge keeps the younger restore ref).
- **Retire.** A test runs the late reap, and the ref is kept, or the decision records the accepted risk.
