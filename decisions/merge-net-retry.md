# Merge network retry

## The question

What does `bin/merge` do when a network error stops a `gh` or `git` call during a merge run?

This is a different question from decision merge-needs-a-proven-head (when a head is proven
to merge). That entry is not changed.

## The ruling

Owner, 2026-10-13, about 16:25 CDT: "Retry 3 times."

- A `gh` network error is retried 3 times. Each retry waits 5 s first.
- After the third retry fails, the run stops with NetStop. The run keeps the claim.
- Only a proven refusal reverts the claim.
- A `git fetch` network error after the claim push also stops the run, with no revert. This is
  the orchestrator's call under the same ruling.

## How it works

Code: `merge/merge.py`.

- `Host.gh` is the one home of every `gh` call. It retries a network error, then raises NetStop.
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

`merge/test_merge.py`, class `GhHalf`. The network cases run from
`test_a_network_error_on_the_wait_read_is_retried_and_the_merge_goes_on` to
`test_a_git_fetch_network_error_after_the_claim_push_stops_without_a_revert`. This record
states no pass result. The gate run holds it.

## Holes, named

Debts: `merge-net-open-reverts` (a merge reply with state OPEN still reverts), `merge-net-5xx-unmatched` (REST 5xx and 429 texts are not network errors), `merge-net-stop-may-have-merged` (the NetStop text says run again after a possible merge), `merge-net-fetch-texts-missed` (some git fetch network texts revert the claim), `merge-net-no-retry-in-deadline` (no retry runs inside `shared_deadline`), `net-error-colon-http-refusal` (a refusal ending in `: HTTP 5xx (url)` reads as a network error), `lock-expiry-read-no-retry` (the lock's expiry read has no retry). Lane `merge-net-holes` takes `merge-net-open-reverts`, `merge-net-5xx-unmatched` and `merge-net-fetch-texts-missed`.

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
