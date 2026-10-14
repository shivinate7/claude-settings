# A missing ref reads as an error while git tracing is on

- **What.** With `GIT_TRACE=1` or `GIT_TRACE2=1` set, git writes to stderr on a missing ref. The missing ref then reads as an error while the variable is set. The ref and its row stay. This was checked on git 2.55.0.windows.3 only.
- **Where.** The stderr check in the purge path of `janitor/sweep.py`.
- **Decision.** `purge-keeps-younger-restore-ref` (the purge keeps the younger restore ref).
- **Retire.** A case with `GIT_TRACE` set reads a missing ref as gone, and the check is run on one more git version.
