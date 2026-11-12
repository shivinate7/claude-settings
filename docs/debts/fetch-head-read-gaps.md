# The FETCH_HEAD read guard misses two likely forms

- **What.** `git pull` followed by a read of FETCH_HEAD in the same command counts as no fetch, so it is refused though the pull fetched. `cat .git/FETCH_HEAD` and a read through `git rev-parse --git-path` pass, so a shared checkout can still return another agent's ref that way.
- **Where.** `fetch_head_read_hit` in `hooks/guard_merge.py`, rule `fetch-head-read`.
- **Decision.** `fetch-head-shared-race` (a FETCH_HEAD read must follow its own fetch).
- **Retire.** Count `git pull` as a fetch for the check, and refuse a `cat` of the `.git` file with the same remedy. Cases for both pass: `hooks/test_guard.py`.
