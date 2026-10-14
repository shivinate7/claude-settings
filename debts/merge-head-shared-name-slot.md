# Two workflow files with one name share a dedup slot

- **What.** Two workflow files with one `name` share one dedup slot. A job-level failure still reaches `classify`.
- **Where.** The dedup in `merge/merge.py`.
- **Decision.** `merge-needs-a-proven-head` (a head is proven only after a check passes on it).
- **Retire.** The dedup key includes the workflow file, and a case with two files of one name keeps both runs.
