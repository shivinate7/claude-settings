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
  extends the lock's expiry past the wait, so no other run can break the lock. A failed extension
  stops the run with NetStop, and the text names the lock.
- After the third retry fails, the run stops with NetStop. The run keeps the claim. Only a proven
  refusal reverts the claim.
- A `git fetch` network error after the claim push also stops the run, with no revert. Run again to resume.

Code: `merge/merge.py`.

- `Host.gh` is the one home of every `gh` call. It retries a network error, then raises NetStop.
- `retry_net` is the one retry loop. `Host.gh`, `GhLock.api` (every lock step) and
  `host_default_branch` call it. `RATE_LIMIT` sends a rate limit to `rate_wait` in place of the 5 s
  pause. A rate text that holds 404 never reads as a gone lock. A lock read that outlasts the
  retries raises NetStop. The guard's head read keeps no retry.
- `rate_wait` gives the wait, from `RATE_LADDER` and the reply headers. `GhLock.api` asks for the
  headers (`gh api -i`). `split_headers` drops the header block before the reply is read.
- `retry_net` runs `before_wait(wait)` before each rate wait. After the take, `confirm` sets
  `Host.before_wait` to `Lock.extend_for`. `GhLock.api` always passes its own `extend_for`. Before
  the take, `extend_for` does nothing, because the lock is not yet the run's.
- `Lock.extend_for(wait)` moves the expiry to now + wait + `LOCK_MARGIN` (300 s). It writes nothing
  when the expiry already covers that. `LOCK_MAX_HOLD` (6 h from the take) is the hard bound: a
  longer hold stops the run.
- An expired lock is never extended: `extend_for` stops the run with no write and no wait.
- The extension calls run once: no retry, no wait. The expired-lock DELETE in `GhLock.acquire` runs
  once too. A late retry could land after another run's take.
- Each extension commit joins `Lock.mine` before its push or PATCH, so `release` deletes the lock
  even when the reply is lost.
- `NET_ERROR` matches only the error-line forms of gh and git. A JSON answer, a PR title or a check
  name never matches.
- `Host.merge` reads state, `mergeCommit` and `headRefOid` after every `gh pr merge` reply. The
  reply alone is not trusted.
  - MERGED at the proven head: success.
  - MERGED at another head: stop, no revert.
  - Unreadable state: NetStop, no revert.
  - Lost reply and state OPEN: NetStop, no revert.
  - Proven refusal: revert.

Reason: a 429 on the lock commit failed merge tries; a retried, bounded wait keeps a healthy merge from stopping.

## Holes, named

Debt: `dead-run-extended-lock-blocks`.

## Platforms

- Windows: `bin/merge.cmd` is the launcher.
- macOS: the README names `bin/merge` as the launcher (`~/.claude/bin`). Proof on the Mac clone is not measured. Linux is unmeasured.

Kind: build
Plan: decisions/merge-net-retry.md#the-ruling (windows)
Plan: decisions/merge-net-retry.md#platforms (macos)
