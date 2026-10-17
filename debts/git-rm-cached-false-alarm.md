# An index-only delete denies

- **What.** `git rm -rf --cached .` denies. It removes files from the index only, not from disk.
- **Where.** `hooks/guard_push_delete.py`.
- **Decision.** `guard-reads-wrapped-commands` (the stream and delete guards read the command a wrapper runs).
- **Retire.** Allow `git rm` with `--cached`.
