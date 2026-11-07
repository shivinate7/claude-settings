# A report after a push names the head's CI state

## The ruling

A turn that pushes a head names that head's CI state in its report. This closes the gap that a report could name a push before its checks finished, under the owner's ruling of 2026-11-07 13:20 CST, a found gap gets a fix, not a note (decision `cull-rules`, the owner's cull of rules). A Stop hook cannot wait without polling, so it reads once: the report must not claim a pending head as done.

- `lint/report_guard.py` names a push after the last human message: `git push` (not a dry run, a delete or a tag push) or the GitHub MCP `push_files`, `create_or_update_file` or `delete_file`. Merges are out; the merge-checks rule covers them. Only the newest head of each branch counts.
- `hooks/ci_wake.py` `head_state` is the one home of the read, a sibling of the CI wake in decision `ci-wait-reads-run-status`. A branch with no open PR, a draft PR, or a head the PR has moved past needs no CI ("none"). A ready PR drops skipped runs (as `wait_for` does), then `judge_runs` judges the rest. A ready PR with no run yet is pending. A push to main reads the head's runs direct; with no run listed it is unknown, since the repo may have no CI.
- Red beats pending: a head with one red run and one running run reads red. A cancelled run alone reads red.
- What the report says, per state:
  - Pending: `CI running on <sha7>` under Next, and no BUILT or RECORDED Done item that names the head. A Done item may cite the PR or an earlier commit.
  - Red: `CI red on <sha7>`, anywhere in the reply.
  - Unknown, a read that failed or ran out of budget: `CI unknown on <sha7>`, anywhere in the reply.
  - Green or none: no line.
- The missing-report marker also holds each head's state, so the rewrite makes no second read.
- Measured 2026-11-07 14:12 CST (cloud): the REST read of a branch's open PR and the run list of a commit both work (route rows `ci-pr-read-gh-api-cloud`, `ci-runs-list-gh-cli-cloud`, `ci-runs-read-gh-api-cloud`).

Cost: only on a Stop after a push that is not a `stop_hook_active` Stop, inside the Stop hook already running. At most 2 gh processes per head (the PR read, the run list), plus 1 git process for a short head on main or a head the push output does not give. 8 s for each read and 20 s for all of them (`ci_wake.Budget`, a clock seam), under the 35 s Stop timeout in `settings.json`. It writes only the existing marker file. It starts no timer and no long-lived process.

Known limit: the shape of a `push_files` result is unmeasured. The guard reads a 40-hex `sha`, then `commit.sha`, then `object.sha`; a result with none of these is not checked. `update_pull_request_branch` names no branch, so it yields no head.

Why: a session could report a push as done while its checks still ran or had failed.

Kind: build
Plan: docs/decisions/push-report-names-ci.md#the-ruling (all)
