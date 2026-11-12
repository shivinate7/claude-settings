# The FETCH_HEAD read guard has known gaps

- **What.** Gaps a shared checkout can still hit. `cat .git/FETCH_HEAD` is no git read and passes. A fetch that fails before a `;` or `|` read still clears it, since the check reads text, not exit codes. `git -C <other> fetch` then a bare read passes, though the fetch moved another checkout's file. An attached `--source=FETCH_HEAD` or `--onto=FETCH_HEAD` is no word the check reads. A fetch and a read in one command still share a window another agent can fetch inside, so the check narrows the race and does not close it. `git pull` then a read is refused though the pull fetched: an over-refusal, not a miss.
- **Where.** `fetch_head_read_hit` in `hooks/guard_merge.py`, rule `fetch-head-read`.
- **Decision.** `fetch-head-shared-race` (a FETCH_HEAD read must follow its own fetch).
- **Retire.** Refuse a `cat` of the `.git` file with the same remedy. Read the `-C` directory of a fetch against the read's. Read `--source=` and `--onto=` values. Count `git pull` as a fetch. Cases for each pass: `hooks/test_guard.py`.
