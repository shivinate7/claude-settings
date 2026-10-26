# c53: the merge tool works from a cloud session

Build thread brief. Written by the build advisor, Oct 26, against claude-settings main 149f4bc
(#574, agents stop their watchers).

## Goal

`merge/merge.py` runs end to end from a claude.ai cloud session, and still runs the same on Mac
and Windows. Then cloud build threads merge their own green PRs under the standing merge grant.

## Why it fails today

In cloud sessions gh reaches GitHub through a proxy. REST calls work (`gh api repos/...`, admin
rights). GraphQL is refused with HTTP 403: "GitHub GraphQL is not available from Claude Code
sessions; use the REST API". `gh auth status` reports a failed login; ignore it, REST still works.
These merge.py calls use GraphQL, so each fails (line numbers at 149f4bc):
- 543 `gh pr view --json headRefOid,headRefName,baseRefName,state,mergeable,mergeStateStatus,isDraft,body`
- 558 `gh pr list --state open --json headRefName,headRefOid,baseRefName`
- 597 `gh pr checks --json name,bucket,link,startedAt,completedAt`
- 790 `gh pr merge --<method> --match-head-commit <sha>`
- 794 `gh pr view --json state,mergeCommit,headRefOid`
- 1141 `gh repo view --json defaultBranchRef`
Line 681 `gh run list` and the lock calls (`gh api -i`) already use REST: check, do not rewrite.

## The change

One home in merge.py for these reads and the merge, on `gh api` REST routes, used on every
platform (no second GraphQL path):
- PR: `GET repos/{o}/{r}/pulls/{n}` (head.sha, head.ref, base.ref, state, merged, draft,
  mergeable, mergeable_state, body). mergeable can be null while GitHub computes it: read again,
  as the tool does today for UNKNOWN.
- Open PRs: `GET repos/{o}/{r}/pulls?state=open&per_page=100`, all pages.
- Checks: `GET repos/{o}/{r}/commits/{sha}/check-runs` (all pages) AND
  `GET repos/{o}/{r}/commits/{sha}/status`. gh pr checks merges both lists; the REST version must
  too, and map each entry to the same buckets (pass, fail, pending, skipping, cancel).
- Merge: `PUT repos/{o}/{r}/pulls/{n}/merge` with `merge_method` and `sha` (the head-match guard).
  Then `GET pulls/{n}` for merged and merge_commit_sha.
- Default branch: `GET repos/{o}/{r}` default_branch.
- Keep every existing retry, rate-limit and network-error path (retry_net, the 5xx and
  rate-limit parsers) on the new calls. Map the old GraphQL enum values (MERGEABLE, CLEAN,
  BLOCKED, DIRTY, ...) to the REST lowercase values in one table.

## Failure classes (outcomes-tests-are-claims)

- The real risk: a check missing from the merged list, or a status mapped to the wrong bucket,
  lets merge.py count a pending or red check as green and merge early. Test: a commit with one
  green check-run and one pending commit status is not green; a failed status is red; a
  required check present only as a status is found.
- A paged list read only on its first page drops checks or PRs. Test with two pages.
- The merge sends no sha, so a push after the read merges unreviewed code. Test: a head change
  between read and merge refuses (GitHub answers 409).
- test_merge.py fakes gh output. Re-point its fakes to the REST shapes; show each new case red
  on 149f4bc and green on the fix.

## Roles

Orchestrate: test-author, builder, fresh reviewer. It changes a gate's verdict (which checks
count as green), so the reviewer hunts the failure classes above. Usual review cap.

## Done when

- CI green on ubuntu, macos and windows (gates.yml, including gates-windows-merge).
- One live read-only run from this cloud session against a real open PR (#577 or #578) prints
  the tool's verdict on mergeability and checks, with no GraphQL error. Do not merge with it from
  the unmerged branch.
- The PR stops at green. Its own merge goes to the owner (merge.py on the Mac), unless the owner
  says otherwise.

## Report (25 lines max)

Done, Deviations, Input Needed, Next. Include the PR, the red-then-green test names, and the
live run's verdict line.
