# The merge rate-limit retry is too short for GitHub's write limit

- **What.** The merge tool retries a rate limit 3 times with a 60 s wait. On 2026-10-14, GitHub's secondary write limit refused the lock commit from 22:41 to past 23:00. Four merge tries of PR 436 failed, including one with the new retry. The run then needs a person to start it again.
- **Where.** `RATE_WAIT_CAP` and `retry_net` in `merge/merge.py`.
- **Decision.** `merge-net-retry` (the merge tool retries a network error or a rate limit, then stops).
- **Retire.** The merge waits out a write limit of at least 20 minutes with no person, or it reads GitHub's reset time. A test with a long fake limit shows the merge goes on.
