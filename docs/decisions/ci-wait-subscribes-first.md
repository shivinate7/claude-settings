# A ready mark warns when the session has not subscribed

## The ruling

Owner, 2026-11-13 21:39 CST, in a batch runner's chat (relayed by the runner and the consultant): "why are u not setting a watcher and or just polling to be woken? why setting check ins". A session that waits on CI calls `subscribe_pr_activity` for the PR first. It keeps one long check-in as a safety net (rule `git-ci-wait-checks-in`).

- `hooks/ready_subscribe_warn.py` is a PreToolUse hook on `mcp__github__update_pull_request`. It acts only on a call with `draft` false, the cloud's ready route. `ci_wake.mcp_ready_calls` parses that call, the one parser of it.
- It reads the session's transcript once, through `lint/_transcript.py`. The last `subscribe_pr_activity` or `unsubscribe_pr_activity` call for that owner, repo and PR number decides. A subscribe as the last word is silence. An unsubscribe, or none, prints one `additionalContext` warning that names `subscribe_pr_activity`.
- It never sets a permissionDecision, so it never refuses the ready mark. It fails open and silent on bad input, a missing transcript or any error.
- A call in a sidechain record counts. A subscribe that sits only in a resumed `api-request-blob` copy does not, because the shared reader yields no call from one. `hooks/test_ready_subscribe_warn.py` pins both (the blob case is the owner lane's ruling).

## The mistake and the harm

A batch runner (runner 10) set timed check-ins on PR 3302 and no subscription. Its run ended at 21:33 CST, and a rerun came at about 21:37 CST (the consultant's account, unchecked). The harm: a late rerun on the top-priority PR. A subscription wakes the session on a finished run with all jobs passed, a comment, and a review. A red run posts a `ci-done` comment, which the subscription also delivers (decision `ci-wait-reads-run-status`).

## Why warn, not refuse

A ready mark with no subscription is not always wrong. A session may mark ready and merge with no wait, because the checks already passed or the owner asked for it. How often that happens is unmeasured. A refusal would stop those sessions, so the hook warns once per ready mark. It is a nudge, and the rule is still a rule.

## Cost

One transcript read per ready mark, with no other process, timer, file or log, pinned by `hooks/test_ready_subscribe_warn.py` (`case_ready_mark_reads_once_and_starts_nothing_else`). A call that is not a ready mark reads no transcript, and the silent cases of the same test prove that gate.
Kind: process
Home: hooks/ready_subscribe_warn.py
