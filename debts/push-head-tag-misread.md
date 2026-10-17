# A tag named like the current branch misreads HEAD

- **What.** `symbolic-ref --short HEAD` prints `heads/<name>` when a tag has the branch's name, so a lease push of `HEAD` allows.
- **Where.** `hooks/guard_push_delete.py`, the current-branch read.
- **Decision.** `default-branch-read-order` (the order that reads a repo's default branch).
- **Retire.** The read drops `--short` and strips `refs/heads/`, and a case with a same-name tag asks.
