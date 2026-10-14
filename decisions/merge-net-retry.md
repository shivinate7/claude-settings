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
  - Proven refusal: revert. Hole 1 names one case that also reverts.
- A `git fetch` network error after the claim push: NetStop. The claim stays. Run again to resume.

## What protects it

`merge/test_merge.py`, class `GhHalf`. The network cases run from
`test_a_network_error_on_the_wait_read_is_retried_and_the_merge_goes_on` to
`test_a_git_fetch_network_error_after_the_claim_push_stops_without_a_revert`. This record
states no pass result. The gate run holds it.

## Holes, named

Review round 3, final, 2026-10-13. Holes 1, 2 and 4 go to fix lane `merge-net-holes`.

1. A `gh pr merge` reply with exit 0 and a state read of OPEN still reverts (`merge/merge.py`
   lines 549-550). A lagging read or a merge queue could revert a merge that landed.
2. REST 5xx texts from `gh api` do not match `NET_ERROR`: `gh: Server Error (HTTP 502)`,
   `gh: HTTP 503`, `HTTP 502 (url)`. HTTP 500, the GraphQL "Something went wrong" text and 429 do
   not match either. In `required_names()`, during the wait, a server error reverts the claim.
3. The NetStop text says "Run again." The merge may have landed. A rerun stops at "is MERGED".
   The after-merge steps (`ff_main`, `afterMerge`, `cut_branch`) do not run.
4. The `git fetch` pattern misses some network texts. Each one reverts the claim: HTTP/2
   INTERNAL_ERROR, Empty reply from server, GnuTLS recv error, Failed sending data to the peer,
   ssh kex_exchange_identification.
5. No retry runs inside `shared_deadline`, which wraps the guard's head read. `Host.gh` sets the
   retry count to 0 there. A network error there reads as unknown.

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
