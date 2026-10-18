# Merge network retry

## The ruling

What `bin/merge` does when a network error or a rate limit stops a `gh` or `git` call. Distinct from
merge-needs-a-proven-head (when a head is proven).

- A `gh` network error is retried 3 times. Each retry waits 5 s first.
- A rate limit is retried 3 times too. A rate limit is a 403 or 429 with GitHub's rate-limit text,
  or a GraphQL rate-limit line. A permission 403 is never retried.
- The rate waits are 60, 300 and 900 s, in that order (21 minutes in all). GitHub's secondary write
  limit can refuse a lock commit for 20 minutes or more.
- GitHub's reset time is the wait in place of the rung, when `gh api -i` gives one. `Retry-After`
  always counts. `X-Ratelimit-Reset` counts only while `X-Ratelimit-Remaining` is 0. A missing,
  unreadable or past value gives the rung. No wait is over 900 s.
- Each rate wait prints one line that names the call and the wait.
- A rate wait is an exception to the lock's 600 s cap. Before each rate wait, the merge tool
  extends the lock's expiry to now + wait + 300 s (`LOCK_MARGIN`), so no other run can break the lock.
  A hold of 6 h from the take (`LOCK_MAX_HOLD`) is the hard bound. A failed extension stops the run with
  NetStop, and the text names the lock.
- An expired lock is never extended: the run stops with no write and no wait. The extension calls and the
  expired-lock DELETE run once, with no retry, because a late retry could land after another run's take.
- After the third retry fails, the run stops with NetStop. The run keeps the claim. Only a proven
  refusal reverts the claim.
- The guard's head read keeps no retry.
- A `git fetch` network error after the claim push also stops the run, with no revert. Run again to resume.
- `Host.merge` reads state, `mergeCommit` and `headRefOid` after every `gh pr merge` reply. The
  reply alone is not trusted.
  - MERGED at the proven head: success.
  - MERGED at another head: stop, no revert.
  - Unreadable state: NetStop, no revert.
  - Lost reply and state OPEN: NetStop, no revert.
  - Proven refusal: revert.

Reason: a 429 on the lock commit failed merge tries; a retried, bounded wait keeps a healthy merge from stopping.

Kind: process
Home: merge/merge.py
