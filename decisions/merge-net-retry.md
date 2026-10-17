# Merge network retry

## The question

What does `bin/merge` do when a network error or a rate limit stops a `gh` or `git` call during a merge run?

This is a different question from decision merge-needs-a-proven-head (when a head is proven
to merge). That entry is not changed.

## The ruling

Owner, 2026-10-13, about 16:25 CDT: "Retry 3 times."

- A `gh` network error is retried 3 times. Each retry waits 5 s first.
- A rate limit is retried 3 times too. A rate limit is a 403 or 429 with GitHub's rate-limit
  text, or a GraphQL rate-limit line. A permission 403 is never retried. This is the
  orchestrator's call under the same ruling, after the incident of 2026-10-14: the merge of PR
  435 failed 7 times at "cannot make the lock commit" on GitHub's secondary write limit. The
  owner, through the coordinator, named a 429 a rate limit too.
- The rate waits are 60, 300 and 900 s, in that order (the ladder, 21 minutes in all). The
  retry count stays 3. The ladder answers the incident of 2026-10-14: GitHub's secondary write
  limit refused the lock commit from 22:41 to past 23:00, and four merge tries of PR 436 failed.
- GitHub's reset time is the wait in place of the rung, when `gh api -i` gives one.
  `Retry-After` always counts. `X-Ratelimit-Reset` counts only while `X-Ratelimit-Remaining`
  is 0. A missing, unreadable or past value gives the rung. No wait is over 900 s.
- Each rate wait prints one line that names the call and the wait.
- A rate wait is an exception to the lock's 600 s cap (the spare in its TTL). Owner, 2026-10-17 01:50 CDT, asked if
  the rate limit can be coded as an exception, and chose "Exception that extends the lock".
  Before each rate wait, the merge tool extends the lock's expiry past the wait, so no other run
  can break the lock. A healthy merge never stops for a rate limit.
- A failed extension stops the run with NetStop, and the text names the lock. The run never
  waits on a lock that could expire.
- After the third retry fails, the run stops with NetStop. The run keeps the claim.
- Only a proven refusal reverts the claim.
- A `git fetch` network error after the claim push also stops the run, with no revert. This is
  the orchestrator's call under the same ruling.

## How it works

Code: `merge/merge.py`.

- `Host.gh` is the one home of every `gh` call. It retries a network error, then raises NetStop.
- `retry_net` is the one retry loop. `Host.gh`, `GhLock.api` (every lock step) and
  `host_default_branch` call it. `RATE_LIMIT` picks the rate wait. A rate text that holds 404
  never reads as a gone lock. A lock read that outlasts the retries raises NetStop.
- The guard's head read keeps no retry.
- `rate_wait` gives the wait, from `RATE_LADDER` and the reply headers. `GhLock.api` asks for
  the headers (`gh api -i`). `split_headers` drops the header block before the reply is read.
  MEASURED 2026-10-17 03:13 CDT: real `gh api -i` output parses with `split_headers` (28
  headers, bare body).
- `retry_net` runs `before_wait(wait)` before each rate wait. After the lock is taken,
  `confirm` sets `Host.before_wait`, and `GhLock.api` passes it, to `Lock.extend_for`.
  Before the take, the lock is not yet the run's, so a rate wait follows the ladder alone: 21
  minutes per call at most.
- `Lock.extend_for(wait)` moves the expiry to now + wait + `LOCK_MARGIN` (300 s). It writes
  nothing when the expiry already covers that. `LOCK_MAX_HOLD` (6 h from the take) is the hard
  bound: a longer hold stops the run.
- An expired lock is never extended. A rival may hold it already, so `extend_for` stops the run
  with no write and no wait.
- The extension calls run once: no retry, no wait. The expired-lock DELETE in `GhLock.acquire`
  runs once too, with no wait. A late retry could land after another run's take.
- Each extension commit joins `Lock.mine` before its push or PATCH. So `release` deletes the
  lock even when the reply to that push or PATCH is lost.
- `NET_ERROR` matches only the error-line forms of gh and git. A JSON answer never matches. A PR
  title or a check name never matches.
- `Host.merge` reads state, `mergeCommit` and `headRefOid` after every `gh pr merge` reply. The
  reply alone is not trusted.
  - MERGED at the proven head: success.
  - MERGED at another head: stop, no revert.
  - Unreadable state: NetStop, no revert.
  - Lost reply and state OPEN: NetStop, no revert.
  - Proven refusal: revert. `merge-net-open-reverts` names one case that also reverts.
- A `git fetch` network error after the claim push: NetStop. The claim stays. Run again to resume.

## What protects it

`merge/test_merge.py`, classes `GhHalf`, `Unlock`, `GhLockRateRetry` and `RateLimitWait`. The
network cases run from `test_a_network_error_on_the_wait_read_is_retried_and_the_merge_goes_on`
to `test_a_git_fetch_network_error_after_the_claim_push_stops_without_a_revert`. Three classes
pin the extension: `LockExtensionReachesHost` (`confirm` hands the host `extend_for`),
`LockExtendsForRateWaits` (`GhLock`) and `GitLockExtendsForRateWaits` (`GitLock`). This record
states no pass result. The gate run holds it.

## Holes, named

Debts: `merge-net-open-reverts` (a merge reply with state OPEN still reverts), `merge-net-5xx-unmatched` (REST 5xx and 429 texts are not network errors), `merge-net-stop-may-have-merged` (the NetStop text says run again after a possible merge), `merge-net-fetch-texts-missed` (some git fetch network texts revert the claim), `merge-net-no-retry-in-deadline` (no retry runs inside `shared_deadline`), `net-error-colon-http-refusal` (a refusal ending in `: HTTP 5xx (url)` reads as a network error), `lock-read-error-never-expires` (a failed lock-commit read gives a lock that never expires). Lane `merge-net-holes` takes `merge-net-open-reverts`, `merge-net-5xx-unmatched` and `merge-net-fetch-texts-missed`.

Rate-wait holes:

- `rate-wait-outside-ttl-budget`: the wait time is not added to the lock's TTL budget. Only
  `LOCK_MAX_HOLD` bounds a long hold.
- `ghlock-no-compare-and-swap`: the `GhLock` PATCH is not compare-and-swap. A lock that expires
  between the check and the PATCH (about 3 calls) could overwrite a rival's fresh lock. The
  expired-lock DELETE has the same window. `GitLock` uses a lease.
- `dead-run-extended-lock-blocks`: a dead run's extended lock blocks other runs up to about 20
  minutes more. `merge --unlock` clears it.
- `expired-delete-net-error-stops`: a network error on the expired-lock DELETE now stops the
  run.

## Build plan

Code in `merge/merge.py`. Cases in `merge/test_merge.py`, class `GhHalf`.

### windows

Built on this machine. `bin/merge.cmd` is the Windows launcher.

### macos

The README names `bin/merge` as the macOS and Linux launcher (`~/.claude/bin`). Proof on the
Mac clone is not measured. Linux is not named in this plan and is also unmeasured.

Kind: build
Plan: decisions/merge-net-retry.md#windows (windows)
Plan: decisions/merge-net-retry.md#macos (macos)
